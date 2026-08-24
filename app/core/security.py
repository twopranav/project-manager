from datetime import datetime, timedelta, timezone
from jose import jwt
from passlib.context import CryptContext
from app.core.config import get_settings

# Load the application's configured secret key, JWT algorithm, and token expiration settings.
settings = get_settings()

# Configure Passlib to hash and verify passwords using bcrypt.
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Hash a plaintext password so only the resulting password hash is stored.
def hash_password(password: str) -> str:
    return pwd_context.hash(password)

# Verify whether a supplied plaintext password matches the stored password hash.
def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)

# Create a signed JWT containing the user's subject identifier and an expiration timestamp.
def create_access_token(subject: str) -> str:
    # Calculate the token expiration time by adding the configured lifetime to the current UTC time.
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    # Encode the subject and expiration into a signed JWT using the configured secret and algorithm.
    return jwt.encode({"sub": subject, "exp": expire}, settings.SECRET_KEY, algorithm=settings.ALGORITHM)