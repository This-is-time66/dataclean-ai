import io
import json
import numpy as np
import pandas as pd
from typing import Dict, Any

from fastapi import HTTPException

from core.config import (
    _ID_EXACT, _ID_SUFFIX, _ID_PREFIX,
    _NAN_STRINGS, _BOOL_TRUE, _BOOL_FALSE, _BOOL_ALL,
    _SENTINEL_CANDIDATES, _NON_NEG_KW,
)
from core.database import client_groq

# =================================================================
# PIPELINE STATE FACTORY
# =================================================================

def make_state(df: pd.DataFrame) -> Dict[str, Any]:
    return {
        "df":               df,
        "analysis_plan":    {},
        "logs":             [],
        "data_description": "",
        "metadata":         {},
        "eda_report":       {},
        "dropped_columns":  [],
    }

# =================================================================
# COLUMN CLASSIFIER HELPERS
# =================================================================

def is_id_like_col(col: str, df: pd.DataFrame) -> bool:
    """
    Returns True if this column is an identifier / free-text label
    that should NEVER be label-encoded.
    """
    c = col.lower().strip()

    if c in _ID_EXACT:
        return True
    if any(c.endswith(s) for s in _ID_SUFFIX):
        return True
    if any(c.startswith(s) for s in _ID_PREFIX):
        return True

    n = len(df)
    if n <= 1:
        return False

    # All-unique numeric → surrogate / auto-increment key
    if pd.api.types.is_numeric_dtype(df[col]):
        if df[col].nunique() == n and df[col].isnull().sum() == 0:
            return True

    # All-unique object → natural key or free-text
    if df[col].dtype == object and df[col].nunique() == n:
        return True

    return False


def is_date_like_col(series: pd.Series) -> bool:
    """
    Returns True if >50% of non-null values can be parsed as dates.
    Excludes bare 4-digit year columns (e.g. 2020, 2021).
    """
    if pd.api.types.is_datetime64_any_dtype(series):
        return True

    sample = series.dropna().astype(str).head(50)
    if len(sample) < 2:
        return False

    # Bare 4-digit years like 2020/2021 are NOT date columns
    if sample.str.match(r"^\d{4}$").mean() > 0.8:
        return False

    try:
        parsed = pd.to_datetime(sample, errors="coerce")
        if parsed.notna().mean() > 0.5:
            return True
    except Exception:
        pass

    patterns = (
        r"^\d{4}-\d{2}-\d{2}",
        r"^\d{2}[/-]\d{2}[/-]\d{4}",
        r"^\d{4}[/-]\d{2}[/-]\d{2}",
        r"^\d{1,2}\s+\w+\s+\d{4}",
        r"^\w+\s+\d{1,2},?\s+\d{4}",
    )
    try:
        return sample.str.match("|".join(patterns)).mean() > 0.5
    except Exception:
        return False


def is_boolean_col(series: pd.Series) -> bool:
    """
    True if column has EXACTLY 2 distinct non-null values
    that both map to True or False from the canonical boolean set.
    """
    non_null = series.dropna()
    if len(non_null) == 0:
        return False
    uniq = {str(v).strip().lower() for v in non_null.unique()}
    if len(uniq) != 2:
        return False
    return uniq <= _BOOL_ALL


def is_free_text_col(col: str, df: pd.DataFrame) -> bool:
    """
    True if column's unique value ratio exceeds 50%
    → too high-cardinality for meaningful label encoding.
    """
    n_unique     = df[col].nunique()
    unique_ratio = n_unique / max(len(df), 1)
    return unique_ratio > 0.5

# =================================================================
# PLAN RULE ENFORCER
# =================================================================

def enforce_plan_rules(df: pd.DataFrame, plan: dict) -> dict:
    """
    Deterministic guard that corrects AI plan errors.
    Step 1 — Validate encode list: remove ids, dates, free-text.
    Step 2 — Remove stale column references.
    Step 3 — Auto-assign every column the AI missed.
    Step 4 — Force-encode low-cardinality / boolean categoricals.
    """
    for key in ("impute_median", "impute_mode", "encode", "ignore"):
        plan.setdefault(key, [])

    # Step 1
    cleaned_encode = []
    for col in list(plan["encode"]):
        if col not in df.columns:
            continue
        if (
            is_id_like_col(col, df) or
            is_date_like_col(df[col]) or
            is_free_text_col(col, df)
        ):
            if col not in plan["ignore"]:
                plan["ignore"].append(col)
        else:
            cleaned_encode.append(col)
    plan["encode"] = cleaned_encode

    # Step 2
    valid = set(df.columns)
    for key in ("impute_median", "impute_mode", "ignore"):
        plan[key] = [c for c in plan[key] if c in valid]

    # Step 3
    all_planned = set(
        plan["impute_median"] + plan["impute_mode"] +
        plan["encode"]        + plan["ignore"]
    )
    for col in df.columns:
        if col in all_planned:
            continue
        if pd.api.types.is_numeric_dtype(df[col]):
            plan["impute_median"].append(col)
        elif (
            is_id_like_col(col, df) or
            is_date_like_col(df[col]) or
            is_free_text_col(col, df)
        ):
            plan["ignore"].append(col)
        else:
            plan["impute_mode"].append(col)

    # Step 4
    for col in df.columns:
        if col in plan["encode"] or col in plan["ignore"]:
            continue
        if pd.api.types.is_numeric_dtype(df[col]):
            continue
        if is_boolean_col(df[col]):
            plan["encode"].append(col)
            if col in plan["impute_mode"]:
                plan["impute_mode"].remove(col)
            continue
        if (
            not is_id_like_col(col, df) and
            not is_date_like_col(df[col]) and
            not is_free_text_col(col, df)
        ):
            plan["encode"].append(col)
            if col in plan["impute_mode"]:
                plan["impute_mode"].remove(col)

    return plan

# =================================================================
# PIPELINE NODES
# =================================================================

def node_preprocessor(state: dict) -> dict:
    """NODE 1 — Raw data normalisation."""
    df      = state["df"].copy()
    dropped = []

    df.columns = [str(c).strip() for c in df.columns]

    nan_map: dict = {}
    for raw in _NAN_STRINGS:
        if raw:
            nan_map[raw]              = np.nan
            nan_map[raw.upper()]      = np.nan
            nan_map[raw.capitalize()] = np.nan

    for col in df.select_dtypes(include=["object"]).columns:
        df[col] = df[col].astype(str).str.strip()
        df[col] = df[col].replace(nan_map)
        df[col] = df[col].replace("", np.nan)
        df[col] = df[col].where(
            df[col].astype(str).str.lower() != "nan", np.nan
        )

    for col in df.select_dtypes(include=["object"]).columns:
        sample = df[col].dropna().head(100)
        if len(sample) == 0:
            continue
        cleaned_sample = (
            sample.astype(str)
            .str.replace(r"[$£€¥,\s%]", "", regex=True)
            .str.strip()
        )
        try:
            converted = pd.to_numeric(cleaned_sample, errors="coerce")
            if converted.notna().mean() >= 0.8:
                df[col] = pd.to_numeric(
                    df[col].astype(str)
                    .str.replace(r"[$£€¥,\s%]", "", regex=True)
                    .str.strip(),
                    errors="coerce",
                )
        except Exception:
            pass

    empty_cols = [c for c in df.columns if df[c].isnull().all()]
    if empty_cols:
        df.drop(columns=empty_cols, inplace=True)
        dropped.extend(empty_cols)
        state["logs"].append(f"Dropped fully-empty columns: {empty_cols}.")

    const_cols = [
        c for c in df.columns
        if df[c].nunique(dropna=True) <= 1 and c not in dropped
    ]
    if const_cols:
        df.drop(columns=const_cols, inplace=True)
        dropped.extend(const_cols)
        state["logs"].append(f"Dropped zero-variance columns: {const_cols}.")

    sparse_cols = [
        c for c in df.columns
        if df[c].isnull().mean() > 0.90 and c not in dropped
    ]
    if sparse_cols:
        df.drop(columns=sparse_cols, inplace=True)
        dropped.extend(sparse_cols)
        state["logs"].append(f"Dropped highly sparse columns (>90% NaN): {sparse_cols}.")

    if len(df.columns) == 0:
        raise ValueError(
            "All columns were removed during preprocessing "
            "(all columns were empty, constant, or >90% missing)."
        )

    for col in df.select_dtypes(include=[np.number]).columns:
        col_lower  = col.lower()
        is_non_neg = any(kw in col_lower for kw in _NON_NEG_KW)
        for sentinel in _SENTINEL_CANDIDATES:
            mask = (df[col] == sentinel)
            if not mask.any():
                continue
            pct = mask.mean()
            if pct >= 0.5:
                continue
            non_sentinel = df.loc[~mask, col].dropna()
            if non_sentinel.empty:
                continue
            q1  = non_sentinel.quantile(0.25)
            q3  = non_sentinel.quantile(0.75)
            iqr = q3 - q1
            is_extreme_outlier  = iqr > 0 and (
                sentinel < (q1 - 3.0 * iqr) or
                sentinel > (q3 + 3.0 * iqr)
            )
            is_invalid_negative = is_non_neg and sentinel < 0
            if is_extreme_outlier or is_invalid_negative:
                n_replaced = int(mask.sum())
                df.loc[mask, col] = np.nan
                state["logs"].append(
                    f"Replaced sentinel {int(sentinel)} → NaN in '{col}' "
                    f"({n_replaced} cell(s))."
                )

    state["df"]              = df
    state["dropped_columns"] = dropped
    state["logs"].append("Preprocessor complete.")
    return state


def node_eda_inspector(state: dict) -> dict:
    """NODE 2 — Compute EDA statistics."""
    df  = state["df"]
    eda = {
        "total_rows":     int(len(df)),
        "total_columns":  int(len(df.columns)),
        "duplicate_rows": int(df.duplicated().sum()),
        "total_missing":  int(df.isnull().sum().sum()),
    }
    col_info: dict = {}
    for col in df.columns:
        info: dict = {
            "dtype":        str(df[col].dtype),
            "unique_count": int(df[col].nunique()),
            "null_count":   int(df[col].isnull().sum()),
        }
        if pd.api.types.is_numeric_dtype(df[col]):
            s = df[col].dropna()
            info.update({
                "mean":   round(float(s.mean()),   4) if not s.empty else None,
                "median": round(float(s.median()), 4) if not s.empty else None,
                "std":    round(float(s.std()),    4) if not s.empty else None,
                "min":    round(float(s.min()),    4) if not s.empty else None,
                "max":    round(float(s.max()),    4) if not s.empty else None,
            })
        else:
            top = df[col].value_counts().head(3)
            info["top_values"] = {str(k): int(v) for k, v in top.items()}
        col_info[col] = info
    eda["columns"] = col_info
    state["eda_report"] = eda
    state["logs"].append("EDA complete.")
    return state


def node_date_handler(state: dict) -> dict:
    """NODE 3 — Parse date-like columns and extract numeric features."""
    df        = state["df"].copy()
    extracted = []

    for col in list(df.columns):
        if pd.api.types.is_numeric_dtype(df[col]):
            continue
        if not is_date_like_col(df[col]):
            continue
        try:
            parsed = pd.to_datetime(df[col], errors="coerce")
            if parsed.notna().mean() < 0.5:
                continue
            if (parsed.dt.month == 1).all() and (parsed.dt.day == 1).all():
                df[col] = parsed.dt.year.astype(float)
                extracted.append(f"{col} (→ year int)")
                continue
            df[f"{col}_year"]      = parsed.dt.year.astype(float)
            df[f"{col}_month"]     = parsed.dt.month.astype(float)
            df[f"{col}_day"]       = parsed.dt.day.astype(float)
            df[f"{col}_dayofweek"] = parsed.dt.dayofweek.astype(float)
            df.drop(columns=[col], inplace=True)
            extracted.append(col)
        except Exception:
            pass

    state["df"] = df
    if extracted:
        state["logs"].append(f"Date features extracted from: {extracted}.")
    return state


def node_ai_planner(state: dict) -> dict:
    """NODE 4 — Ask Llama 3 to draft a cleaning plan, then enforce rules."""
    df     = state["df"]
    prompt = (
        f"You are a Data Architect. Given these columns: {list(df.columns)}\n"
        "Return ONLY a valid JSON object with exactly these four keys:\n"
        '{"impute_median": [], "impute_mode": [], "encode": [], "ignore": []}\n'
        "Rules:\n"
        "- impute_median: numeric columns with missing values\n"
        "- impute_mode: categorical columns with missing values\n"
        "- encode: low-cardinality categorical columns to label-encode\n"
        "- ignore: id columns, free-text, dates, high-cardinality text\n"
        "No extra keys or explanation. Only valid JSON."
    )
    try:
        resp = client_groq.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0,
        )
        plan = json.loads(resp.choices[0].message.content)
    except Exception:
        plan = {}

    plan = enforce_plan_rules(df, plan)
    state["analysis_plan"] = plan
    state["logs"].append(
        f"AI Planner: encode={len(plan['encode'])}, "
        f"impute_median={len(plan['impute_median'])}, "
        f"impute_mode={len(plan['impute_mode'])}, "
        f"ignore={len(plan['ignore'])}."
    )
    return state


def node_logic_cleaner(state: dict) -> dict:
    """NODE 5 — Deduplication + imputation."""
    df   = state["df"].copy()
    plan = state["analysis_plan"]

    id_cols    = [c for c in df.columns if is_id_like_col(c, df)]
    dedup_cols = [c for c in df.columns if c not in id_cols] or None
    before_n   = len(df)
    df = df.drop_duplicates(subset=dedup_cols).reset_index(drop=True)
    if len(df) < before_n:
        state["logs"].append(
            f"Deduplication removed {before_n - len(df)} duplicate row(s)."
        )

    for col in plan.get("impute_median", []):
        if (
            col in df.columns and
            pd.api.types.is_numeric_dtype(df[col]) and
            df[col].isnull().any()
        ):
            df[col] = df[col].fillna(df[col].median())

    for col in plan.get("impute_mode", []):
        if col in df.columns and df[col].isnull().any():
            mode_val = df[col].mode()
            if not mode_val.empty:
                df[col] = df[col].fillna(mode_val[0])

    state["df"] = df
    state["logs"].append("Cleaning/imputation complete.")
    return state


def node_outlier_capper(state: dict) -> dict:
    """NODE 6 — IQR-based outlier capping for every numeric column."""
    df     = state["df"].copy()
    capped = []

    for col in df.select_dtypes(include=[np.number]).columns:
        if is_id_like_col(col, df):
            continue
        if df[col].isnull().all():
            continue
        if df[col].nunique() <= 3:
            continue
        q1  = df[col].quantile(0.25)
        q3  = df[col].quantile(0.75)
        iqr = q3 - q1
        if iqr == 0:
            continue
        lower = q1 - 1.5 * iqr
        upper = q3 + 1.5 * iqr
        n_out = int(((df[col] < lower) | (df[col] > upper)).sum())
        if n_out > 0:
            df[col] = df[col].clip(lower=lower, upper=upper)
            capped.append(f"{col} ({n_out})")

    state["df"] = df
    if capped:
        state["logs"].append(f"Outlier capping applied: {', '.join(capped)}.")
    else:
        state["logs"].append("Outlier check: no outliers found.")
    return state


def node_feature_encoder(state: dict) -> dict:
    """NODE 7 — Label-encode columns listed in plan['encode']."""
    df   = state["df"].copy()
    plan = state["analysis_plan"]

    bool_map = {v: 1 for v in _BOOL_TRUE}
    bool_map.update({v: 0 for v in _BOOL_FALSE})

    for col in plan.get("encode", []):
        if col not in df.columns:
            continue

        if df[col].isnull().any():
            mode_val = df[col].mode()
            if not mode_val.empty:
                df[col] = df[col].fillna(mode_val[0])

        if df[col].dtype == object:
            df[col] = df[col].astype(str).str.strip().str.lower()

        if is_boolean_col(df[col]):
            df[f"{col}_encoded"] = (
                df[col].astype(str).str.strip().str.lower()
                .map(bool_map)
                .fillna(0)
                .astype(int)
            )
        else:
            df[f"{col}_encoded"] = (
                df[col].astype("category").cat.codes.clip(lower=0)
            )

    state["df"] = df
    state["logs"].append("Feature encoding complete.")
    return state


def node_ai_storyteller(state: dict) -> dict:
    """NODE 8 — Produce a plain-English summary via Llama 3."""
    prompt = (
        "You are a data analyst. Summarise this CSV cleaning pipeline "
        "in exactly 2 clear, concise sentences for a non-technical audience.\n"
        f"Pipeline logs: {state['logs']}\n"
        f"Columns encoded: {state['analysis_plan'].get('encode', [])}\n"
        f"Dropped columns: {state.get('dropped_columns', [])}"
    )
    try:
        resp = client_groq.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
        )
        state["data_description"] = resp.choices[0].message.content.strip()
    except Exception:
        state["data_description"] = (
            "The dataset was successfully cleaned: missing values were imputed, "
            "outliers were capped, and categorical features were encoded."
        )
    return state

# =================================================================
# PIPELINE RUNNER
# =================================================================

PIPELINE = [
    node_preprocessor,
    node_eda_inspector,
    node_date_handler,
    node_ai_planner,
    node_logic_cleaner,
    node_outlier_capper,
    node_feature_encoder,
    node_ai_storyteller,
]

def run_pipeline(df: pd.DataFrame) -> Dict[str, Any]:
    state = make_state(df)
    for node in PIPELINE:
        state = node(state)
    return state

# =================================================================
# SERIALISATION HELPERS
# =================================================================

def make_serializable(obj):
    if isinstance(obj, dict):
        return {k: make_serializable(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [make_serializable(i) for i in obj]
    if isinstance(obj, (np.integer, np.int64)):
        return int(obj)
    if isinstance(obj, (np.floating, np.float64)):
        return float(obj)
    if isinstance(obj, float) and np.isnan(obj):
        return None
    try:
        if pd.isna(obj):
            return None
    except Exception:
        pass
    return obj


def read_csv_safe(contents: bytes) -> pd.DataFrame:
    for enc in ("utf-8", "utf-8-sig", "latin-1", "cp1252"):
        try:
            return pd.read_csv(io.BytesIO(contents), encoding=enc)
        except UnicodeDecodeError:
            continue
    raise HTTPException(
        status_code=400,
        detail="Could not decode CSV. Try saving as UTF-8.",
    )