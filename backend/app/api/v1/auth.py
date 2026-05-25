
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from app.database import get_db
from app.models.user import User
from app.dependencies import get_current_user
import jwt, os, uuid, hashlib, hmac
from datetime import datetime, timedelta

router = APIRouter(prefix="/auth", tags=["auth"])
JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret-change-in-production")
JWT_ALGO = "HS256"
PW_PEPPER = os.getenv("PW_PEPPER", "wealthos-pepper")

class SignupRequest(BaseModel):
    email: str; password: str; full_name: str; firm_name: Optional[str] = None

class LoginRequest(BaseModel):
    email: str; password: str

def _hash(pw): return hmac.new(PW_PEPPER.encode(), pw.encode(), hashlib.sha256).hexdigest()
def _token(uid, email): return jwt.encode({"sub":uid,"email":email,"exp":datetime.utcnow()+timedelta(hours=24)}, JWT_SECRET, algorithm=JWT_ALGO)
def _out(u, token=None):
    d = {"id":u.id,"email":u.email,"full_name":u.full_name,"firm_name":u.firm_name}
    return {"access_token":token,"token_type":"bearer","user":d} if token else d

@router.post("/signup", status_code=201)
def signup(req: SignupRequest, db: Session = Depends(get_db)):
    if db.query(User).filter(User.email==req.email.lower()).first():
        raise HTTPException(400, "Email already registered")
    u = User(id=str(uuid.uuid4()), email=req.email.lower(), hashed_password=_hash(req.password),
             full_name=req.full_name, firm_name=req.firm_name)
    db.add(u); db.commit(); db.refresh(u)
    return _out(u, _token(u.id, u.email))

@router.post("/login")
def login(req: LoginRequest, db: Session = Depends(get_db)):
    u = db.query(User).filter(User.email==req.email.lower(), User.is_active==True).first()
    if not u or u.hashed_password != _hash(req.password):
        raise HTTPException(401, "Invalid email or password")
    return _out(u, _token(u.id, u.email))

@router.get("/me")
def me(current_user: User = Depends(get_current_user)):
    return _out(current_user)
