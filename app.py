import hashlib
import io
import json
from datetime import datetime
from typing import Optional, Dict, Any

import numpy as np
from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from core.auth import get_current_user, get_optional_user
from core.config import MAX_FILE_SIZE
from core.database import supabase
from core.models import LoginRequest, SignupRequest
from core.auth import hash_password, verify_password, create_token
from core.pipeline import make_serializable, read_csv_safe, run_pipeline

# =================================================================
# APP SETUP
# =================================================================
app = FastAPI(title="Agentic CSV Data Analyst", version="3.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")

# In-memory cache: file_hash → {df, filename}
_pipeline_cache: Dict[str, Any] = {}


def get_file_hash(contents: bytes) -> str:
    return hashlib.md5(contents).hexdigest()

# =================================================================
# HEALTH CHECK
# =================================================================

@app.get("/health")
async def health():
    return {"status": "ok", "version": "3.0.0"}

# =================================================================
# AUTH ENDPOINTS
# =================================================================

@app.post("/auth/signup")
async def signup(body: SignupRequest):
    existing = supabase.table("users").select("id").eq("email", body.email).execute()
    if existing.data:
        raise HTTPException(status_code=400, detail="Email already registered.")
    if len(body.password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters.")
    hashed = hash_password(body.password)
    result = supabase.table("users").insert({
        "email":      body.email,
        "password":   hashed,
        "full_name":  body.full_name,
        "created_at": datetime.utcnow().isoformat(),
    }).execute()
    if not result.data:
        raise HTTPException(status_code=500, detail="Failed to create account.")
    user  = result.data[0]
    token = create_token(user["id"], user["email"])
    return {
        "token":     token,
        "user_id":   user["id"],
        "email":     user["email"],
        "full_name": user["full_name"],
    }


@app.post("/auth/login")
async def login(body: LoginRequest):
    result = supabase.table("users").select("*").eq("email", body.email).execute()
    if not result.data:
        raise HTTPException(status_code=401, detail="Invalid email or password.")
    user = result.data[0]
    if not verify_password(body.password, user["password"]):
        raise HTTPException(status_code=401, detail="Invalid email or password.")
    token = create_token(user["id"], user["email"])
    return {
        "token":     token,
        "user_id":   user["id"],
        "email":     user["email"],
        "full_name": user["full_name"],
    }


@app.get("/auth/me")
async def get_me(current_user: dict = Depends(get_current_user)):
    result = (
        supabase.table("users")
        .select("id, email, full_name, created_at")
        .eq("id", current_user["sub"])
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="User not found.")
    return result.data[0]


@app.delete("/auth/account")
async def delete_account(current_user: dict = Depends(get_current_user)):
    user_id = current_user["sub"]
    try:
        supabase.table("analyses").delete().eq("user_id", user_id).execute()
        supabase.table("users").delete().eq("id", user_id).execute()
        return {"status": "deleted"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete account: {e}")

# =================================================================
# HISTORY ENDPOINTS
# =================================================================

@app.get("/history")
async def get_history(current_user: dict = Depends(get_current_user)):
    result = (
        supabase.table("analyses")
        .select(
            "id, file_name, original_rows, original_cols, "
            "cleaned_rows, cleaned_cols, summary, created_at"
        )
        .eq("user_id", current_user["sub"])
        .order("created_at", desc=True)
        .limit(50)
        .execute()
    )
    return result.data or []


@app.get("/history/{analysis_id}")
async def get_history_item(
    analysis_id: str,
    current_user: dict = Depends(get_current_user),
):
    result = (
        supabase.table("analyses")
        .select("*")
        .eq("id", analysis_id)
        .eq("user_id", current_user["sub"])
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Analysis not found.")
    item = result.data[0]
    for field in ("eda_report", "logs", "cleaned_columns"):
        if isinstance(item.get(field), str):
            try:
                item[field] = json.loads(item[field])
            except Exception:
                pass
    return item


@app.delete("/history/{analysis_id}")
async def delete_history_item(
    analysis_id: str,
    current_user: dict = Depends(get_current_user),
):
    supabase.table("analyses").delete()\
        .eq("id", analysis_id)\
        .eq("user_id", current_user["sub"])\
        .execute()
    return {"status": "deleted"}

# =================================================================
# CORE ENDPOINTS
# =================================================================

@app.post("/analyze")
async def analyze_csv(
    file: UploadFile = File(...),
    current_user: Optional[dict] = Depends(get_optional_user),
):
    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only .csv files are accepted.")

    contents = await file.read()
    if len(contents) == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")
    if len(contents) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="File exceeds the 1 MB limit.")

    try:
        df = read_csv_safe(contents)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to parse CSV: {e}")

    if df.empty or len(df.columns) == 0:
        raise HTTPException(status_code=400, detail="CSV has no data.")

    try:
        final_state = run_pipeline(df)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Pipeline error: {e}")

    cleaned_df = final_state["df"]
    records    = cleaned_df.replace({np.nan: None}).to_dict(orient="records")

    result = make_serializable({
        "status":          "success",
        "original_shape":  {"rows": len(df),         "columns": len(df.columns)},
        "cleaned_shape":   {"rows": len(cleaned_df), "columns": len(cleaned_df.columns)},
        "eda_report":      final_state["eda_report"],
        "logs":            final_state["logs"],
        "summary":         final_state["data_description"],
        "cleaned_columns": list(cleaned_df.columns),
        "cleaned_data":    records,
        "dropped_columns": final_state.get("dropped_columns", []),
    })

    # Cache by file-hash so /download always returns the same result
    file_hash = get_file_hash(contents)
    _pipeline_cache[file_hash] = {
        "df":       cleaned_df,
        "filename": file.filename,
    }

    # Persist to Supabase (logged-in users only)
    if current_user:
        try:
            supabase.table("analyses").insert({
                "user_id":         current_user["sub"],
                "file_name":       file.filename,
                "original_rows":   len(df),
                "original_cols":   len(df.columns),
                "cleaned_rows":    len(cleaned_df),
                "cleaned_cols":    len(cleaned_df.columns),
                "summary":         final_state["data_description"],
                "eda_report":      json.dumps(result["eda_report"]),
                "logs":            json.dumps(final_state["logs"]),
                "cleaned_columns": json.dumps(list(cleaned_df.columns)),
                "cleaned_data":    json.dumps(records[:500]),
                "created_at":      datetime.utcnow().isoformat(),
            }).execute()
        except Exception as e:
            print(f"Warning: Failed to save analysis to DB: {e}")

    return JSONResponse(content=result)


@app.post("/download")
async def download_clean_csv(file: UploadFile = File(...)):
    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only .csv files are accepted.")

    contents = await file.read()
    if len(contents) == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")
    if len(contents) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="File exceeds the 1 MB limit.")

    file_hash = get_file_hash(contents)

    if file_hash in _pipeline_cache:
        cleaned_df = _pipeline_cache[file_hash]["df"]
        fname      = _pipeline_cache[file_hash]["filename"]
    else:
        # Cache miss — re-run the pipeline
        try:
            df = read_csv_safe(contents)
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Failed to parse CSV: {e}")
        try:
            final_state = run_pipeline(df)
            cleaned_df  = final_state["df"]
            fname       = file.filename
            _pipeline_cache[file_hash] = {"df": cleaned_df, "filename": fname}
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Pipeline error: {e}")

    stream = io.StringIO()
    cleaned_df.to_csv(stream, index=False)
    return StreamingResponse(
        io.BytesIO(stream.getvalue().encode("utf-8")),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=cleaned_{fname}"},
    )

# =================================================================
# SERVE FRONTEND
# =================================================================

@app.get("/")
async def read_index():
    return FileResponse("templates/index.html")