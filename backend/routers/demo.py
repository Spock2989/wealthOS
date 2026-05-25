from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
import uuid
from database import get_db
from models import DemoRequest
from auth import require_admin

router = APIRouter()

class DemoLeadRequest(BaseModel):
    ref_id:         str
    name:           str
    firm:           str
    email:          str
    phone:          str
    role:           Optional[str] = None
    aum:            Optional[str] = None
    clients:        Optional[str] = None
    preferred_slot: Optional[str] = None
    message:        Optional[str] = None
    source:         Optional[str] = None

@router.post("/demo-requests")
def submit_demo(body: DemoLeadRequest, db: Session = Depends(get_db)):
    existing = db.query(DemoRequest).filter(
        DemoRequest.email == body.email.lower()
    ).order_by(DemoRequest.created_at.desc()).first()
    if existing:
        from datetime import timedelta, timezone
        age = datetime.now(timezone.utc) - existing.created_at.replace(tzinfo=timezone.utc)
        if age.days < 7:
            return {"status": "duplicate", "ref_id": existing.ref_id}
    lead = DemoRequest(
        ref_id=body.ref_id or "WOS-" + uuid.uuid4().hex[:8].upper(),
        name=body.name, firm=body.firm,
        email=body.email.lower(), phone=body.phone,
        role=body.role, aum=body.aum, clients=body.clients,
        preferred_slot=body.preferred_slot,
        message=body.message, source=body.source,
    )
    db.add(lead); db.commit(); db.refresh(lead)
    return {"status": "ok", "ref_id": lead.ref_id}

@router.get("/demo-requests")
def list_leads(
    status: Optional[str] = None,
    skip: int = 0, limit: int = 100,
    db: Session = Depends(get_db),
    _: object = Depends(require_admin)
):
    q = db.query(DemoRequest)
    if status:
        q = q.filter(DemoRequest.status == status)
    leads = q.order_by(DemoRequest.created_at.desc()).offset(skip).limit(limit).all()
    return [_serialize(l) for l in leads]

@router.patch("/demo-requests/{lead_id}")
def update_lead(
    lead_id: str, body: dict,
    db: Session = Depends(get_db),
    _: object = Depends(require_admin)
):
    lead = db.query(DemoRequest).filter(DemoRequest.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    for k, v in body.items():
        if k in {"status", "notes"}:
            setattr(lead, k, v)
    db.commit(); db.refresh(lead)
    return _serialize(lead)

def _serialize(l):
    return {
        "id": l.id, "ref_id": l.ref_id, "name": l.name,
        "firm": l.firm, "email": l.email, "phone": l.phone,
        "role": l.role, "aum": l.aum, "clients": l.clients,
        "preferred_slot": l.preferred_slot, "message": l.message,
        "source": l.source, "status": l.status, "notes": l.notes,
        "created_at": l.created_at.isoformat() if l.created_at else None,
    }