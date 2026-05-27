"""
WealthOS — Demo Request API
POST /api/v1/demo-requests   (public — no auth required)
GET  /api/v1/demo-requests   (admin only — requires JWT)
"""

from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy import Column, String, Text, DateTime
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
import uuid

from app.database import get_db, Base
from app.dependencies import get_current_user
from app.models.user import User

router = APIRouter(prefix="/demo-requests", tags=["demo"])


# ── Model ──────────────────────────────────────────────────────────
class DemoRequest(Base):
    __tablename__ = "demo_requests"
    id             = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    ref_id         = Column(String(32), unique=True, nullable=False)
    name           = Column(String(256), nullable=False)
    firm           = Column(String(256), nullable=False)
    email          = Column(String(256), nullable=False, index=True)
    phone          = Column(String(64), nullable=False)
    role           = Column(String(64), nullable=True)
    aum            = Column(String(64), nullable=True)
    clients        = Column(String(64), nullable=True)
    preferred_slot = Column(String(64), nullable=True)
    message        = Column(Text, nullable=True)
    source         = Column(String(64), nullable=True)
    status         = Column(String(32), default="new")
    created_at     = Column(DateTime, default=datetime.utcnow)


# ── Schemas ─────────────────────────────────────────────────────────
class DemoRequestIn(BaseModel):
    ref_id:         Optional[str] = None
    name:           str
    firm:           str
    email:          str
    phone:          str
    role:           Optional[str] = None
    aum:            Optional[str] = None
    clients:        Optional[str] = None
    slot:           Optional[str] = None          # frontend sends "slot"
    preferred_slot: Optional[str] = None          # or "preferred_slot"
    message:        Optional[str] = None
    source:         Optional[str] = None


def _serialize(d: DemoRequest):
    return {
        "id": d.id, "ref_id": d.ref_id, "name": d.name, "firm": d.firm,
        "email": d.email, "phone": d.phone, "role": d.role,
        "aum": d.aum, "clients": d.clients,
        "preferred_slot": d.preferred_slot,
        "message": d.message, "source": d.source,
        "status": d.status,
        "created_at": d.created_at.isoformat() if d.created_at else None,
    }


# ── POST /demo-requests ─────────────────────────────────────────────
@router.post("/", status_code=201)
def submit_demo(body: DemoRequestIn, db: Session = Depends(get_db)):
    # Dedupe: same email within 7 days → return existing ref_id
    existing = db.query(DemoRequest).filter(
        DemoRequest.email == body.email.strip().lower()
    ).order_by(DemoRequest.created_at.desc()).first()

    if existing:
        from datetime import timedelta
        age = datetime.utcnow() - existing.created_at
        if age.days < 7:
            return {"status": "received", "ref_id": existing.ref_id}

    slot = body.preferred_slot or body.slot or "flexible"
    ref  = (body.ref_id or "").strip() or "WOS-" + uuid.uuid4().hex[:8].upper()

    lead = DemoRequest(
        ref_id         = ref,
        name           = body.name.strip(),
        firm           = body.firm.strip(),
        email          = body.email.strip().lower(),
        phone          = body.phone.strip(),
        role           = body.role,
        aum            = body.aum,
        clients        = body.clients,
        preferred_slot = slot,
        message        = body.message,
        source         = body.source,
    )
    db.add(lead)
    db.commit()
    db.refresh(lead)

    # Fire email alert — best-effort, never blocks response
    try:
        from app.services.email_service import alert_new_demo_request
        alert_new_demo_request(
            ref_id  = lead.ref_id,
            name    = lead.name,
            firm    = lead.firm,
            email   = lead.email,
            phone   = lead.phone,
            role    = lead.role or "",
            aum     = lead.aum or "",
            clients = lead.clients or "",
            slot    = lead.preferred_slot or "",
            message = lead.message or "",
            source  = lead.source or "",
        )
    except Exception:
        pass  # email never fails the request

    return {"status": "ok", "ref_id": lead.ref_id}


# ── GET /demo-requests ─────────────────────────────────────────────
@router.get("/")
def list_leads(
    status: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Admin endpoint — requires valid JWT (any logged-in advisor)."""
    q = db.query(DemoRequest)
    if status:
        q = q.filter(DemoRequest.status == status)
    leads = q.order_by(DemoRequest.created_at.desc()).offset(skip).limit(limit).all()
    return {"count": len(leads), "leads": [_serialize(l) for l in leads]}
