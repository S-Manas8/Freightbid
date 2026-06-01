from jose import jwt, JWTError
from fastapi import HTTPException, Header
from sqlalchemy.orm import Session
import datetime

SECRET_KEY = "your-super-secret-key-change-in-production"
ALGORITHM = "HS256"


def create_token(user_id: str, role: str) -> str:
    payload = {
        "sub": user_id,
        "role": role,
        "exp": datetime.datetime.utcnow() + datetime.timedelta(days=7)
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


def get_current_user(authorization: str = Header(None)) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authorization header missing")
    token = authorization.split(" ")[1]
    return decode_token(token)


def require_role(required_role: str):
    def checker(authorization: str = Header(None)):
        current = get_current_user(authorization)
        if current["role"] != required_role:
            raise HTTPException(status_code=403, detail=f"Only {required_role}s can do this")
        return current
    return checker