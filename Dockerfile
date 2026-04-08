# ── Base image ────────────────────────────────────────────────────
FROM python:3.10-slim

# ── Working directory inside the container ────────────────────────
WORKDIR /app

# ── System deps (needed by bcrypt / some pip wheels) ─────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# ── Python dependencies first (cached layer) ─────────────────────
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── Copy application code ─────────────────────────────────────────
COPY app.py .
COPY core/ ./core/
COPY templates/ ./templates/
COPY static/ ./static/

# ── Hugging Face Spaces requires port 7860 ────────────────────────
EXPOSE 7860

# ── Launch FastAPI with uvicorn ───────────────────────────────────
#    • host 0.0.0.0  → reachable from outside the container
#    • port 7860     → required by Hugging Face Spaces
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "7860"]