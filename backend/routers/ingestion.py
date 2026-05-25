from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime
import shutil, os, uuid
from database import get_db
from models import Portfolio, Holding, IngestionJob
from auth import get_current_user
from engines.cas_parser import parse_cas_pdf
from engines.normalization import normalize_instrument

router = APIRouter()
UPLOAD_DIR = "/tmp/wealthos_uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

@router.post("/portfolios/{portfolio_id}/upload")
async def upload_cas(
    portfolio_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    portfolio = db.query(Portfolio).filter(
        Portfolio.id == portfolio_id,
        Portfolio.user_id == user.id,
        Portfolio.is_active == True
    ).first()
    if not portfolio:
        raise HTTPException(status_code=404, detail="Portfolio not found")

    job_id   = str(uuid.uuid4())
    ext      = os.path.splitext(file.filename)[1].lower()
    tmp_path = os.path.join(UPLOAD_DIR, f"{job_id}{ext}")

    with open(tmp_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    job = IngestionJob(
        id=job_id, portfolio_id=portfolio_id,
        user_id=user.id, filename=file.filename,
        file_type="cas_pdf" if ext == ".pdf" else "excel",
        status="processing",
    )
    db.add(job); db.commit()

    try:
        if ext != ".pdf":
            raise HTTPException(status_code=400, detail="Only PDF supported currently")

        raw_holdings = parse_cas_pdf(tmp_path)
        if not raw_holdings:
            job.status = "failed"
            job.errors = {"message": "No holdings found in file"}
            db.commit()
            raise HTTPException(status_code=422, detail="No holdings extracted")

        db.query(Holding).filter(Holding.portfolio_id == portfolio_id).delete()

        total_value = 0.0
        for raw in raw_holdings:
            instrument = normalize_instrument(raw, db)
            h = Holding(
                portfolio_id=portfolio_id,
                instrument_id=instrument.id,
                folio_number=raw.get("folio"),
                units=raw.get("units"),
                nav=raw.get("nav"),
                value=raw.get("value", 0.0),
                source="cas_pdf",
                holding_date=datetime.utcnow(),
            )
            db.add(h)
            total_value += raw.get("value", 0.0)

        portfolio.total_value = total_value
        portfolio.updated_at  = datetime.utcnow()

        for h in db.query(Holding).filter(Holding.portfolio_id == portfolio_id).all():
            h.weight = (h.value / total_value * 100) if total_value > 0 else 0

        job.status = "done"
        job.holdings_found = len(raw_holdings)
        job.completed_at = datetime.utcnow()
        db.commit()

        return {
            "status": "ok", "job_id": job_id,
            "holdings_parsed": len(raw_holdings),
            "total_value": total_value,
        }

    except HTTPException:
        raise
    except Exception as e:
        job.status = "failed"
        job.errors = {"message": str(e)}
        db.commit()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

@router.get("/portfolios/{portfolio_id}/jobs")
def list_jobs(portfolio_id: str, db: Session = Depends(get_db), user=Depends(get_current_user)):
    jobs = db.query(IngestionJob).filter(
        IngestionJob.portfolio_id == portfolio_id,
        IngestionJob.user_id == user.id
    ).order_by(IngestionJob.created_at.desc()).limit(10).all()
    return [{
        "id": j.id, "filename": j.filename, "status": j.status,
        "holdings_found": j.holdings_found, "errors": j.errors,
        "created_at": j.created_at.isoformat() if j.created_at else None,
    } for j in jobs]