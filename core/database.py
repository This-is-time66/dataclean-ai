from groq import Groq
from supabase import create_client, Client
from core.config import GROQ_API_KEY, SUPABASE_URL, SUPABASE_KEY

# =================================================================
# VALIDATION
# =================================================================
if not all([GROQ_API_KEY, SUPABASE_URL, SUPABASE_KEY]):
    raise RuntimeError(
        "Missing Environment Secrets! "
        "Set GROQ_API_KEY, SUPABASE_URL, SUPABASE_KEY in your .env file "
        "(local) or Hugging Face Space secrets (production)."
    )

# =================================================================
# CLIENT INSTANCES  (imported by pipeline.py and app.py)
# =================================================================
client_groq: Groq    = Groq(api_key=GROQ_API_KEY)
supabase:    Client  = create_client(SUPABASE_URL, SUPABASE_KEY)