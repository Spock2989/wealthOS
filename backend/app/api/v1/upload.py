
from fastapi import APIRouter, UploadFile, File, HTTPException, BackgroundTasks, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.services.portfolio_service import PortfolioService
from app.parsers.base_parser import ParserRegistry
from app.parsers.cas_parser import CASParser
from app.parsers.excel_parser import ExcelParser
from app.normalizer.normalizer import PortfolioNormalizer
from app.analytics.engine import AnalyticsEngine
import logging, os

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/upload", tags=["upload"])
registry = ParserRegistry()
registry.register(CASParser())
registry.register(ExcelParser())
normalizer = PortfolioNormalizer()
engine = AnalyticsEngine()

@router.post("/")
async def upload(background_tasks: BackgroundTasks, file: UploadFile = File(...),
                 db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in {".pdf",".xlsx",".xls",".csv"}:
        raise HTTPException(400, f"Unsupported file type: {ext}")
    content = await file.read()
    if len(content) > 50*1024*1024: raise HTTPException(400, "File exceeds 50MB")
    if len(content) < 100: raise HTTPException(400, "File appears empty")
    svc = PortfolioService(db)
    p = svc.create(advisor_id=current_user.id, name=file.filename, filename=file.filename)
    background_tasks.add_task(_pipeline, p.id, content, file.filename)
    return {"portfolio_id": p.id, "status": "processing"}

def _pipeline(portfolio_id, content, filename):
    from app.database import SessionLocal
    db = SessionLocal()
    svc = PortfolioService(db)
    try:
        svc.set_status(portfolio_id, "parsing")
        parser = registry.get_parser(content, filename)
        raw = parser.parse(content)
        if not raw: svc.set_status(portfolio_id, "error", "No holdings found"); return
        svc.set_status(portfolio_id, "normalizing")
        canonical = normalizer.normalize(raw)
        if not canonical: svc.set_status(portfolio_id, "error", "Normalization failed"); return
        total = sum(h.current_value for h in canonical)
        svc.save_holdings(portfolio_id, canonical, total)
        svc.set_status(portfolio_id, "analyzing")
        result = engine.run(canonical)
        svc.save_snapshot(portfolio_id, result)
        svc.set_status(portfolio_id, "ready")
    except Exception as e:
        logger.exception(e)
        svc.set_status(portfolio_id, "error", str(e))
    finally:
        db.close()

@router.get("/status/{portfolio_id}")
def status(portfolio_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    svc = PortfolioService(db)
    p = svc.get(portfolio_id, current_user.id)
    if not p: raise HTTPException(404, "Not found")
    return {"portfolio_id": p.id, "status": p.status, "error": p.error_message,
            "holding_count": svc.holding_count(p.id), "total_value": p.total_value}
