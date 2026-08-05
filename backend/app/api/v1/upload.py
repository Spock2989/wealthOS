"""
WealthOS upload route — wired to Universal Ingestion v2.

Backwards-compatible: the legacy ParserRegistry path is kept as a hard
fallback if ingestion_v2 returns zero holdings AND no structured error
(should not happen, but we never silently fail the user).
"""
from fastapi import APIRouter, UploadFile, File, HTTPException, BackgroundTasks, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.services.portfolio_service import PortfolioService
from app.parsers.ingestion_v2 import ingest as ingest_v2
from app.parsers.base_parser import ParserRegistry
from app.parsers.cas_parser import CASParser
from app.parsers.excel_parser import ExcelParser
from app.normalizer.normalizer import PortfolioNormalizer
from app.analytics.engine import AnalyticsEngine
import logging, os

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/upload", tags=["upload"])

# Legacy registry — kept as a fallback only.
_legacy_registry = ParserRegistry()
_legacy_registry.register(CASParser())
_legacy_registry.register(ExcelParser())

normalizer = PortfolioNormalizer()
engine = AnalyticsEngine()


@router.post("/")
async def upload(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    allow_duplicate: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in {".pdf", ".xlsx", ".xls", ".csv", ".docx"}:
        raise HTTPException(400, f"Unsupported file type: {ext}")
    content = await file.read()
    if len(content) > 50 * 1024 * 1024:
        raise HTTPException(400, "File exceeds 50MB")
    if len(content) < 100:
        raise HTTPException(400, "File appears empty")
    svc = PortfolioService(db)

    # Duplicate guard. Re-uploading the same CAS silently created a second
    # portfolio with identical holdings ('portfolio kt.pdf' vs
    # 'portfolio_kt.pdf' both existed in prod), doubling the dashboard.
    # 409 rather than a hard block — a refreshed monthly CAS legitimately
    # reuses its filename, so the caller can retry with allow_duplicate=true.
    if not allow_duplicate:
        existing = svc.find_by_filename(current_user.id, file.filename)
        if existing:
            raise HTTPException(
                409,
                detail={
                    "error": "duplicate_upload",
                    "message": (
                        f"'{file.filename}' was already uploaded on "
                        f"{existing.created_at:%Y-%m-%d %H:%M} UTC. "
                        "Re-send with allow_duplicate=true to upload it again."
                    ),
                    "existing_portfolio_id": existing.id,
                    "existing_created_at":   existing.created_at.isoformat() if existing.created_at else None,
                    "existing_holding_count": svc.holding_count(existing.id),
                },
            )

    p = svc.create(advisor_id=current_user.id, name=file.filename, filename=file.filename)
    background_tasks.add_task(_pipeline, p.id, content, file.filename)
    return {"portfolio_id": p.id, "status": "processing"}


def _pipeline(portfolio_id, content: bytes, filename: str):
    """
    Ingestion → Normalization → Analytics, with full structured error reporting.
    Sets portfolio.status + portfolio.error_message at every transition so the
    frontend can show a precise failure reason instead of a generic 'failed'.
    """
    from app.database import SessionLocal
    db = SessionLocal()
    svc = PortfolioService(db)
    try:
        svc.set_status(portfolio_id, "parsing")
        result = ingest_v2(content, filename)

        if result.error:
            svc.set_status(portfolio_id, "error", f"ingestion: {result.error}")
            return

        raw = result.holdings
        if not raw:
            # Last-chance legacy fallback before giving up.
            try:
                parser = _legacy_registry.get_parser(content, filename)
                raw = parser.parse(content) or []
            except Exception:
                raw = []
            if not raw:
                detail = (
                    f"No holdings detected. format={result.format} "
                    f"broker={result.broker_detected} "
                    f"sheets={result.sheets_or_pages} "
                    f"warnings={result.warnings}"
                )
                svc.set_status(portfolio_id, "error", detail)
                return

        svc.set_status(portfolio_id, "normalizing")
        canonical = normalizer.normalize(raw)
        if not canonical:
            svc.set_status(portfolio_id, "error", "Normalization produced no holdings")
            return

        total = sum(h.current_value for h in canonical)
        svc.save_holdings(portfolio_id, canonical, total)
        svc.set_status(portfolio_id, "analyzing")
        analytics_result = engine.run(canonical)
        svc.save_snapshot(portfolio_id, analytics_result)
        svc.set_status(portfolio_id, "ready")
        logger.info(
            "ingest_ok portfolio=%s broker=%s holdings=%s total=%.2f",
            portfolio_id, result.broker_detected, len(canonical), total,
        )
    except Exception as e:
        logger.exception("pipeline_crash")
        svc.set_status(portfolio_id, "error", f"pipeline: {e}")
    finally:
        db.close()


@router.post("/preview")
async def preview(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    """
    Dry-run ingestion — returns the parsed holdings + parser report without
    writing anything to the database. Lets the UI show 'we detected 12 funds
    totalling ₹12.7L from your Zerodha export — proceed?' before commit.
    """
    content = await file.read()
    if len(content) < 100:
        raise HTTPException(400, "File appears empty")
    if len(content) > 50 * 1024 * 1024:
        raise HTTPException(400, "File exceeds 50MB")
    result = ingest_v2(content, file.filename or "")
    return result.to_dict()


@router.get("/status/{portfolio_id}")
def status(
    portfolio_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    svc = PortfolioService(db)
    p = svc.get(portfolio_id, current_user.id)
    if not p:
        raise HTTPException(404, "Not found")
    return {
        "portfolio_id": p.id,
        "status": p.status,
        "error": p.error_message,
        "holding_count": svc.holding_count(p.id),
        "total_value": p.total_value,
    }
