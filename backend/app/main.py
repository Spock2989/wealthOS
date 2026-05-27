from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.models.user import User
from app.models.client import Client
from app.models.portfolio import Portfolio
from app.models.holding import Holding
from app.models.analytics_snapshot import AnalyticsSnapshot
from app.models.ai_report import AIReport
from app.database import create_tables
from app.api.v1 import auth, upload, portfolios, analytics_routes, insights, reports, demo
app = FastAPI(title="WealthOS API", version="2.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
@app.on_event("startup")
def startup():
    create_tables()
app.include_router(auth.router, prefix="/api/v1")
app.include_router(upload.router, prefix="/api/v1")
app.include_router(portfolios.router, prefix="/api/v1")
app.include_router(analytics_routes.router, prefix="/api/v1")
app.include_router(insights.router, prefix="/api/v1")
app.include_router(reports.router, prefix="/api/v1")
app.include_router(demo.router, prefix="/api/v1")
@app.get("/health")
def health():
    return {"status": "ok", "service": "wealthos-api", "version": "2.0.0", "db": "sqlite"}
