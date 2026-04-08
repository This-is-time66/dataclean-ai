import os
from dotenv import load_dotenv

load_dotenv()

# =================================================================
# ENVIRONMENT VARIABLES
# =================================================================
GROQ_API_KEY     = os.environ.get("GROQ_API_KEY")
SUPABASE_URL     = os.environ.get("SUPABASE_URL")
SUPABASE_KEY     = os.environ.get("SUPABASE_KEY")
JWT_SECRET       = os.environ.get("JWT_SECRET", "your-super-secret-jwt-key-change-this")
JWT_ALGORITHM    = "HS256"
JWT_EXPIRE_HOURS = 24 * 7
MAX_FILE_SIZE    = 1 * 1024 * 1024  # 1 MB

# =================================================================
# PIPELINE CONSTANTS
# =================================================================

# Exact column names treated as identifiers — never encode these
_ID_EXACT = frozenset([
    "id", "name", "index", "row_id", "record_id", "uid", "uuid",
    "key", "code", "ref", "reference", "serial", "no", "num",
    "number", "identifier", "username", "user_name", "login",
    "email", "phone", "address", "url", "link", "ip", "mac",
    "description", "comment", "note", "notes", "remarks", "bio",
    "message", "title", "label", "tag", "text", "content",
    "first_name", "last_name", "full_name", "fname", "lname",
])

# Column names that END with these suffixes → identifier
_ID_SUFFIX = (
    "_id", "_key", "_code", "_ref", "_no", "_num",
    "_name", "_uid", "_uuid", "_hash", "_email", "_phone",
    "_url", "_address", "_description", "_text",
)

# Column names that START with these prefixes → identifier
_ID_PREFIX = ("id_", "key_", "ref_", "no_", "num_", "pk_")

# String values that represent missing data
_NAN_STRINGS = frozenset([
    "nan", "null", "none", "na", "n/a", "n.a.", "n.a", "na/a",
    "#na", "#n/a", "#null!", "nil", "-", "--", "---", "?", "??",
    "unknown", "unk", "missing", "not available", "not applicable",
    "not known", "n.k.", "nk", "undefined", "none available",
    "not provided", "not specified", "tbd", "tba", "pending",
])

# Boolean text maps
_BOOL_TRUE  = frozenset(["true",  "yes", "y", "1", "t", "on",  "positive", "enabled",  "active"])
_BOOL_FALSE = frozenset(["false", "no",  "n", "0", "f", "off", "negative", "disabled", "inactive"])
_BOOL_ALL   = _BOOL_TRUE | _BOOL_FALSE

# Numeric sentinel candidates to detect and replace with NaN
_SENTINEL_CANDIDATES = [-999.0, -9999.0, -99.0, -9.0, 9999.0, 99999.0, -1111.0, 999999.0, -8888.0]

# Column name keywords implying non-negative values
_NON_NEG_KW = frozenset([
    "age", "salary", "price", "cost", "amount", "count", "quantity",
    "revenue", "income", "weight", "height", "score", "rate", "fee",
    "total", "sum", "duration", "distance", "size", "length", "width",
    "population", "number", "num", "budget", "spend", "spending",
])