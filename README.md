# DataClean AI — Agentic CSV Data Analyst

An intelligent, multi-node AI pipeline that cleans, analyses, and encodes CSV datasets automatically. Built with **FastAPI**, **Groq (Llama)**, and **Supabase**.

---

## 📁 Project Structure

```
dataclean-ai/
├── app.py                  # FastAPI entry point — all routes & middleware
├── core/
│   ├── config.py           # Env vars & pipeline constants
│   ├── database.py         # Supabase & Groq client initialisation
│   ├── models.py           # Pydantic request schemas
│   ├── auth.py             # JWT & password helpers, FastAPI dependencies
│   └── pipeline.py         # All 8 pipeline nodes + run_pipeline + helpers
├── static/
│   ├── css/
│   │   └── style.css
│   └── js/
│       └── script.js
├── templates/
│   └── index.html
├── .env            # Copy → .env for local dev
├── Dockerfile              # Container config for Hugging Face Spaces
├── .dockerignore
├── .gitignore
├── requirements.txt
└── README.md
```

---

## ⚙️ Pipeline Architecture

| Node | File | Responsibility |
|------|------|----------------|
| 1 · Preprocessor | `core/pipeline.py` | NaN normalisation, sentinel replacement |
| 2 · EDA Inspector | `core/pipeline.py` | Statistics before structural changes |
| 3 · Date Handler | `core/pipeline.py` | Parse dates → year/month/day/dayofweek features |
| 4 · AI Planner | `core/pipeline.py` | Llama  draft plan + deterministic rule enforcer |
| 5 · Logic Cleaner | `core/pipeline.py` | Smart dedup + median/mode imputation |
| 6 · Outlier Capper | `core/pipeline.py` | IQR-based clipping |
| 7 · Feature Encoder | `core/pipeline.py` | Boolean + label encoding |
| 8 · AI Storyteller | `core/pipeline.py` | Plain-English summary via Llama  |

---

## 🖥️ Run Locally (VS Code)

### Prerequisites
- Python 3.10+
- VS Code with the **Python** extension
- A Groq API key and a Supabase project


### Database Setup 
```sql
-- ================================================================
-- TABLE: users
-- ================================================================
CREATE TABLE IF NOT EXISTS users (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email       TEXT NOT NULL UNIQUE,
    password    TEXT NOT NULL,         -- bcrypt hashed
    full_name   TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Index for fast login lookup by email
CREATE INDEX IF NOT EXISTS idx_users_email ON users (email);


-- ================================================================
-- TABLE: analyses
-- ================================================================
CREATE TABLE IF NOT EXISTS analyses (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id          UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    file_name        TEXT NOT NULL,
    original_rows    INTEGER,
    original_cols    INTEGER,
    cleaned_rows     INTEGER,
    cleaned_cols     INTEGER,
    summary          TEXT,
    eda_report       TEXT,             -- JSON stored as text
    logs             TEXT,             -- JSON stored as text
    cleaned_columns  TEXT,             -- JSON stored as text
    cleaned_data     TEXT,             -- JSON stored as text (first 500 rows)
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Index for fast per-user history queries (ordered by date)
CREATE INDEX IF NOT EXISTS idx_analyses_user_created ON analyses (user_id, created_at DESC);

```

### Step-by-step

```bash
# 1. Clone / open the project folder in VS Code
cd dataclean-ai

# 2. Create a virtual environment
python -m venv venv

# Activate — Windows (PowerShell)
venv\Scripts\Activate.ps1

# Activate — macOS / Linux
source venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Create your .env file

# Then open .env and fill in your actual keys

# 5. Start the development server
python app.py
```

---


---

## 🚀 Deploy on Hugging Face Spaces

### 1 · Create a new Space

1. Go to [huggingface.co/spaces](https://huggingface.co/spaces) → **Create new Space**
2. Choose **Docker** as the SDK
3. Set visibility to **Public** (or Private)

### 2 · Add your secrets

In your Space → **Settings** → **Repository secrets**, add:

| Name | Value |
|------|-------|
| `GROQ_API_KEY` | Your Groq key |
| `SUPABASE_URL` |Your Supabase project URL |
| `SUPABASE_KEY` | Your Supabase anon key |


> ⚠️ Never push your `.env` file to Hugging Face. Use secrets only.

### 3 · Push your code

```bash
# Add the HF remote (replace with your Space URL)
git remote add hf https://huggingface.co/spaces/YOUR_USERNAME/YOUR_SPACE_NAME

# Push
git add .
git commit -m "initial deploy"
git push hf main
```

Hugging Face will automatically build the Docker image and start the container on **port 7860**.

### 4 · Check logs

Space → **Logs** tab → watch the build and runtime output.

---

## 🔑 Environment Variables Reference

| Variable | Required | Description |
|----------|----------|-------------|
| `GROQ_API_KEY` | ✅ | Groq cloud API key |
| `SUPABASE_URL` | ✅ | Your Supabase project URL |
| `SUPABASE_KEY` | ✅ | Supabase anon/public key |




---

## 🛠️ Troubleshooting

| Problem | Fix |
|---------|-----|
| `Missing Environment Secrets!` | Check `.env` exists locally or secrets are set on HF |
| Port conflict locally | Change `--port 8000` to another free port |
| HF build fails | Check **Logs** tab; usually a missing requirement or wrong port |
| Static files 404 | Ensure `static/` folder exists with `css/` and `js/` subdirs |