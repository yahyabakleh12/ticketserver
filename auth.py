from datetime import datetime, timedelta
from jose import JWTError, jwt
from passlib.context import CryptContext

SECRET_KEY = "your-very-secret"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

# ``bcrypt`` silently truncates passwords longer than 72 bytes which caused
# ``ValueError`` during verification when the client submitted long passwords
# (e.g. pre-hashed credentials).  ``bcrypt_sha256`` safely pre-hashes the
# password before handing it to ``bcrypt`` and therefore supports arbitrary
# length passwords while remaining backward compatible with existing bcrypt
# hashes.  We keep the plain ``bcrypt`` scheme so that any previously stored
# hashes continue to verify successfully.
pwd_context = CryptContext(
    schemes=["bcrypt_sha256", "bcrypt"],
    deprecated="auto",
)

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: timedelta | None = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=15))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
