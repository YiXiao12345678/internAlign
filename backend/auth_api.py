"""Account routes (signup / login / me) and the `get_current_user` dependency."""
import re
from datetime import datetime, timedelta, timezone

import bcrypt
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from . import config
from .database import get_db
from .models import User

router = APIRouter(tags=["auth"])

# auto_error=False lets us return one consistent 401 message below.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login", auto_error=False)

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MAX_PASSWORD_BYTES = 72  # bcrypt ignores (and bcrypt>=5 rejects) anything longer


def _validate_email(value: str) -> str:
    value = value.strip().lower()
    if not _EMAIL_RE.match(value):
        raise ValueError("Enter a valid email address")
    return value


class SignUpRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    email: str
    password: str

    @field_validator("email")
    @classmethod
    def _check_email(cls, value: str) -> str:
        return _validate_email(value)

    @field_validator("name")
    @classmethod
    def _clean_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Name is required")
        return value


class LoginRequest(BaseModel):
    email: str
    password: str

    @field_validator("email")
    @classmethod
    def _check_email(cls, value: str) -> str:
        return _validate_email(value)


def hash_password(password: str) -> str:
    # NOTE: this uses `bcrypt` directly instead of passlib. passlib 1.7.4 is
    # unmaintained and crashes with bcrypt >= 5 ("password cannot be longer than
    # 72 bytes" raised from its internal self-test), which breaks signup/login.
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:  # password too long or malformed hash
        return False


def create_token(user_id: int) -> str:
    expires = datetime.now(timezone.utc) + timedelta(minutes=config.TOKEN_EXPIRE_MINUTES)
    return jwt.encode({"sub": str(user_id), "exp": expires}, config.SECRET_KEY, algorithm=config.ALGORITHM)


def public_user(user: User) -> dict:
    return {"id": user.id, "name": user.name, "email": user.email}


def get_current_user(
    token: str | None = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    """Dependency for any route that needs a logged-in user."""
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Your session has expired. Please log in again.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not token:
        raise unauthorized
    try:
        payload = jwt.decode(token, config.SECRET_KEY, algorithms=[config.ALGORITHM])
        user_id = int(payload["sub"])
    except (JWTError, KeyError, ValueError):
        raise unauthorized

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise unauthorized
    return user


@router.post("/signup", status_code=status.HTTP_201_CREATED)
def signup(request: SignUpRequest, db: Session = Depends(get_db)):
    if len(request.password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")
    if len(request.password.encode("utf-8")) > MAX_PASSWORD_BYTES:
        raise HTTPException(status_code=400, detail="Password must be 72 bytes or fewer")
    if db.query(User).filter(User.email == request.email).first():
        raise HTTPException(status_code=400, detail="An account with this email already exists")

    user = User(name=request.name, email=request.email, hashed_password=hash_password(request.password))
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"message": "Account created successfully", "user": public_user(user)}


@router.post("/login")
def login(request: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == request.email).first()
    if not user or not verify_password(request.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password")
    return {"access_token": create_token(user.id), "token_type": "bearer", "user": public_user(user)}


@router.get("/me")
def me(user: User = Depends(get_current_user)):
    return public_user(user)
