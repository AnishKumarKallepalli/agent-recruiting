"""
Ava — AI Recruiting Agent
FastAPI backend
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from routers import webhooks, dashboard, test

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.info("Ava backend starting up...")
    yield
    logging.info("Ava backend shutting down.")


app = FastAPI(title="Ava — AI Recruiting Agent", lifespan=lifespan)

app.include_router(webhooks.router)
app.include_router(dashboard.router)
app.include_router(test.router)

# Serve the dashboard HTML
app.mount("/static", StaticFiles(directory="dashboard"), name="static")


@app.get("/")
def serve_dashboard():
    return FileResponse("dashboard/index.html")


@app.get("/health")
def health():
    return {"status": "ok", "agent": "Ava"}
