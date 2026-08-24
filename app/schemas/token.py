from pydantic import BaseModel

# Output schema for a successful login response; token_type defaults to the bearer authentication scheme.
class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"

# Schema for decoded JWT payload data; the token subject is optional at the schema-validation level.
class TokenPayload(BaseModel):
    sub: str | None = None