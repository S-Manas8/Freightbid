from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session
import bcrypt
from ..database import get_db
from ..models import User
from ..auth_utils import create_token, get_current_user

router = APIRouter()

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode('utf-8'), hashed.encode('utf-8'))


@router.post("/register")
def register(data: dict, db: Session = Depends(get_db)):
    """
    Register a new user.
    Body: { name, email, password, role, phone }
    role must be "shipper" or "driver"
    """
    if data.get("role") not in ["shipper", "driver"]:
        raise HTTPException(400, "role must be 'shipper' or 'driver'")

    if db.query(User).filter(User.email == data["email"]).first():
        raise HTTPException(400, "Email already registered")

    user = User(
        name=data["name"],
        email=data["email"],
        password=hash_password(data["password"]),
        role=data["role"],
        phone=data.get("phone", ""),
        # Only drivers must undergo KYC, shippers are auto-verified
        kyc_status="verified" if data.get("role") == "shipper" else "pending",
        verification="yes" if data.get("role") == "shipper" else "no",
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_token(user.id, user.role)
    return {
        "message": "Registered successfully",
        "token": token,
        "role": user.role,
        "name": user.name,
        "id": user.id,
        "kyc_status": user.kyc_status or "pending",
        "verification": user.verification or "no",
    }


@router.post("/login")
def login(data: dict, db: Session = Depends(get_db)):
    """
    Login with email + password.
    Body: { email, password }
    Returns JWT token + role for frontend routing.
    """
    user = db.query(User).filter(User.email == data["email"]).first()

    if not user or not verify_password(data["password"], user.password):
        raise HTTPException(401, "Invalid email or password")

    # Only verified drivers can log in to the platform
    if user.role == "driver" and user.verification != "yes":
        raise HTTPException(403, "Login denied: Driver is not verified (eKYC required)")

    token = create_token(user.id, user.role)
    return {
        "token": token,
        "role": user.role,
        "name": user.name,
        "id": user.id,
        "kyc_status": user.kyc_status or "pending",
        "verification": user.verification or "no",
    }
