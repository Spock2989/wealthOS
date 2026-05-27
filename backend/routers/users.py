"""
WealthOS — Auth Router
Full signup, login, email verification, password reset
"""
import os
import secrets
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import Column, String, Boolean, DateTime
from database import get_db, Base
from auth import hash_password, verify_password, create_token, get_current_user

router = APIRouter(prefix="/v1/auth", tags=["auth"])

APP_URL = os.getenv("APP_URL", "https://wlthos.in")
API_URL = os.getenv("API_URL", "https://api.wlthos.in")

# ── Token tables ──────────────────────────────────────────────────
class EmailVerificationToken(Base):
    __tablename__ = "email_verification_tokens"
    token = Column(String, primary_key=True)
    email = Column(String, nullable=False, index=True)
    expires_at = Column(String)
    used = Column(Boolean, default=False)

class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"
    token = Column(String, primary_key=True)
    email = Column(String, nullable=False, index=True)
    expires_at = Column(String)
    used = Column(Boolean, default=False)

# ── Schemas ───────────────────────────────────────────────────────
class RegisterRequest(BaseModel):
    full_name: str
    email: str
    password: str
    firm_name: str = ""
    role: str = "Advisor"

class LoginRequest(BaseModel):
    email: str
    password: str

class ForgotRequest(BaseModel):
    email: str

class ResetRequest(BaseModel):
    token: str
    new_password: str

class ResendRequest(BaseModel):
    email: str

# ── Helpers ───────────────────────────────────────────────────────
def get_user(db, email: str):
    from models import User
    return db.query(User).filter(User.email == email.lower().strip()).first()

def make_token():
    return secrets.token_urlsafe(32)

async def send_verify_email(email: str, name: str, token: str):
    try:
        from email_service import send_email, verification_email
        subj, html = verification_email(name, email, token)
        await send_email(email, subj, html)
    except Exception as e:
        print(f"Email send skip: {e}")

async def send_welcome_email(email: str, name: str):
    try:
        from email_service import send_email, welcome_email
        subj, html = welcome_email(name, email)
        await send_email(email, subj, html)
    except Exception as e:
        print(f"Welcome email skip: {e}")

async def send_reset_email(email: str, name: str, token: str):
    try:
        from email_service import send_email, password_reset_email
        subj, html = password_reset_email(name, token)
        await send_email(email, subj, html)
    except Exception as e:
        print(f"Reset email skip: {e}")

# ── Register ──────────────────────────────────────────────────────
@router.post("/register", status_code=201)
async def register(req: RegisterRequest, db: Session = Depends(get_db)):
    from models import User
    email = req.email.lower().strip()
    if get_user(db, email):
        raise HTTPException(400, "An account with this email already exists.")
    if len(req.password) < 8:
        raise HTTPException(400, "Password must be at least 8 characters.")
    user = User(
        email=email,
        name=req.full_name.strip(),
        password_hash=hash_password(req.password),
        is_active=True,
    )
    # Add optional fields safely
    try:
        user.firm = req.firm_name.strip()
        user.role = req.role
    except Exception:
        pass
    db.add(user)
    db.commit()
    return {"message": "Account created successfully.", "email": email}

# ── Verify ────────────────────────────────────────────────────────
@router.get("/verify", response_class=HTMLResponse)
async def verify_email(token: str = Query(...), db: Session = Depends(get_db)):
    tok = db.query(EmailVerificationToken).filter(
        EmailVerificationToken.token == token,
        EmailVerificationToken.used == False
    ).first()
    if not tok:
        return _page(False, "Invalid or expired link.", False)
    if datetime.utcnow() > datetime.fromisoformat(tok.expires_at):
        return _page(False, "Link expired. Request a new one.", False)
    user = get_user(db, tok.email)
    if not user:
        return _page(False, "Account not found.", False)
    user.is_active = True
    tok.used = True
    db.commit()
    await send_welcome_email(user.email, user.name)
    return _page(True, f"Verified! Welcome to WealthOS, {user.name.split()[0]}.", True)

def _page(ok, msg, redirect):
    color = "#16A34A" if ok else "#DC2626"
    icon = "✓" if ok else "✗"
    redir = f'<script>setTimeout(()=>window.location.href="{APP_URL}/app.html",3000)</script><p style="font-size:12px;color:#5c6480;margin-top:10px">Redirecting in 3s...</p>' if redirect else f'<p style="margin-top:16px"><a href="{APP_URL}/app.html" style="color:#1E40FF;font-size:13px">← Login</a></p>'
    return f'<!DOCTYPE html><html><head><meta charset="UTF-8"/><title>WealthOS</title><link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap" rel="stylesheet"/><style>body{{margin:0;background:#0a0c10;font-family:Inter,sans-serif;display:flex;align-items:center;justify-content:center;min-height:100vh}}.c{{background:#111318;border:1px solid #232839;border-radius:12px;padding:40px;text-align:center;max-width:360px;width:90%}}.i{{width:52px;height:52px;border-radius:50%;background:{color}22;border:2px solid {color};display:flex;align-items:center;justify-content:center;font-size:20px;font-weight:700;color:{color};margin:0 auto 16px}}h2{{color:#e8ecf4;font-size:19px;margin:0 0 8px}}p{{color:#9ba3bc;font-size:13px;line-height:1.6;margin:0}}</style></head><body><div class="c"><div class="i">{icon}</div><h2>{"Verified!" if ok else "Failed"}</h2><p>{msg}</p>{redir}</div></body></html>'

# ── Login ─────────────────────────────────────────────────────────
@router.post("/login")
async def login(req: LoginRequest, db: Session = Depends(get_db)):
    user = get_user(db, req.email)
    if not user or not verify_password(req.password, user.password_hash):
        raise HTTPException(401, "Invalid email or password.")
    is_active = getattr(user, "is_active", True)
    if not is_active:
        raise HTTPException(403, "Account inactive. Contact support.")
    token = create_token(user_id=user.id)
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "email": user.email,
            "full_name": user.name,
            "firm_name": getattr(user, "firm", ""),
            "role": getattr(user, "role", "Advisor"),
        }
    }

# ── Me ────────────────────────────────────────────────────────────
@router.get("/me")
async def me(current_user=Depends(get_current_user)):
    return {
        "email": current_user.email,
        "full_name": current_user.name,
        "firm_name": getattr(current_user, "firm", ""),
        "role": getattr(current_user, "role", "Advisor"),
    }

# ── Resend verify ─────────────────────────────────────────────────
@router.post("/resend-verify")
async def resend_verify(req: ResendRequest, db: Session = Depends(get_db)):
    user = get_user(db, req.email)
    if not user or user.is_active:
        return {"message": "If registered and unverified, a new link has been sent."}
    db.query(EmailVerificationToken).filter(
        EmailVerificationToken.email == req.email.lower(),
        EmailVerificationToken.used == False
    ).update({"used": True})
    tok = make_token()
    db.add(EmailVerificationToken(
        token=tok, email=req.email.lower(),
        expires_at=(datetime.utcnow() + timedelta(hours=24)).isoformat(), used=False
    ))
    db.commit()
    await send_verify_email(user.email, user.name, tok)
    return {"message": "Verification email sent."}

# ── Forgot password ───────────────────────────────────────────────
@router.post("/forgot-password")
async def forgot_password(req: ForgotRequest, db: Session = Depends(get_db)):
    user = get_user(db, req.email)
    if user:
        db.query(PasswordResetToken).filter(
            PasswordResetToken.email == req.email.lower(),
            PasswordResetToken.used == False
        ).update({"used": True})
        tok = make_token()
        db.add(PasswordResetToken(
            token=tok, email=req.email.lower(),
            expires_at=(datetime.utcnow() + timedelta(hours=1)).isoformat(), used=False
        ))
        db.commit()
        await send_reset_email(user.email, user.name, tok)
    return {"message": "If registered, a reset link has been sent."}

# ── Reset password ────────────────────────────────────────────────
@router.post("/reset-password")
async def reset_password(req: ResetRequest, db: Session = Depends(get_db)):
    tok = db.query(PasswordResetToken).filter(
        PasswordResetToken.token == req.token,
        PasswordResetToken.used == False
    ).first()
    if not tok or datetime.utcnow() > datetime.fromisoformat(tok.expires_at):
        raise HTTPException(400, "Invalid or expired reset link.")
    if len(req.new_password) < 8:
        raise HTTPException(400, "Password must be at least 8 characters.")
    user = get_user(db, tok.email)
    if not user:
        raise HTTPException(404, "Account not found.")
    user.password_hash = hash_password(req.new_password)
    tok.used = True
    db.commit()
    return {"message": "Password updated. You can now log in."}
