from pydantic import BaseModel

# =================================================================
# REQUEST SCHEMAS
# =================================================================

class SignupRequest(BaseModel):
    email:     str
    password:  str
    full_name: str


class LoginRequest(BaseModel):
    email:    str
    password: str