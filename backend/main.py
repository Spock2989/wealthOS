from fastapi import FastAPI
from database import engine, Base
from routers import demo, users, portfolios, ingestion

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="WealthOS API",
    version="1.6.0",
    description="Institutional portfolio intelligence infrastructure for Indian wealth management"
)

# CORS is handled exclusively by nginx reverse proxy.
# Do NOT add FastAPI CORSMiddleware — it causes duplicate Access-Control headers
# which browsers (especially Safari) reject with "Load failed".

app.include_router(demo.router)
app.include_router(users.router)
app.include_router(portfolios.router)
app.include_router(ingestion.router)

# Session 3 routers
try:
    from routers import data as data_router
    app.include_router(data_router.router)
except Exception as e:
    print(f"data router skip: {e}")

try:
    from routers import memos as memos_router
    app.include_router(memos_router.router)
except Exception as e:
    print(f"memos router skip: {e}")

@app.get("/health")
def health():
    return {"status": "ok", "service": "wealthos-api", "version": "1.0.0"}
