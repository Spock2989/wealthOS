"""
WealthOS API — Production Entry Point v2.0
Switched from legacy routers/ to app/ backend stack.

CORS is handled exclusively by Nginx (api.wlthos.in config).
Do NOT add CORSMiddleware here — duplicate headers break Safari.

Database defaults to SQLite. Override by setting DATABASE_URL in .env.
For PostgreSQL: DATABASE_URL=postgresql://wealthos:PASSWORD@localhost/wealthosdb
"""

import os
import sys

# Ensure backend/ is on sys.path so `from app.xxx import` resolves
# when uvicorn is launched from /opt/wlthos/backend/
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Default to SQLite — override in .env when PostgreSQL is provisioned
os.environ.setdefault("DATABASE_URL", "sqlite:///./wealthos.db")

from fastapi import FastAPI

# Import all models so SQLAlchemy metadata is populated before create_tables()
from app.models.user import User                          # noqa: F401
from app.models.client import Client                      # noqa: F401
from app.models.portfolio import Portfolio                # noqa: F401
from app.models.holding import Holding                    # noqa: F401
from app.models.analytics_snapshot import AnalyticsSnapshot  # noqa: F401
from app.models.ai_report import AIReport                 # noqa: F401
from app.api.v1.demo import DemoRequest                   # noqa: F401  (registers table)

from app.database import create_tables
from app.api.v1 import auth, upload, portfolios, analytics_routes, insights, reports, scenarios, lookthrough
from app.api.v1 import demo                                # demo-requests lead capture

app = FastAPI(
    title="WealthOS API",
    version="2.0.0",
    description="Institutional portfolio intelligence infrastructure for Indian wealth management",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS is handled exclusively by Nginx reverse proxy — do NOT add CORSMiddleware


@app.on_event("startup")
def startup():
    """Create all tables on first boot. Safe on existing DB — skips tables that exist."""
    create_tables()


# v1 API routes
app.include_router(auth.router,             prefix="/api/v1")
app.include_router(upload.router,           prefix="/api/v1")
app.include_router(portfolios.router,       prefix="/api/v1")
app.include_router(analytics_routes.router, prefix="/api/v1")
app.include_router(insights.router,         prefix="/api/v1")
app.include_router(reports.router,          prefix="/api/v1")
app.include_router(scenarios.router,        prefix="/api/v1")
app.include_router(lookthrough.router,      prefix="/api/v1")
app.include_router(demo.router,             prefix="/api/v1")


@app.get("/health")
def health():
    db_type = os.environ.get("DATABASE_URL", "sqlite").split(":")[0]
    return {"status": "ok", "service": "wealthos-api", "version": "2.0.0", "db": db_type}
