# main.py

import logging
import logging.config
import os
import pathlib
from dotenv import load_dotenv

# ─── 1) Load .env before ANYTHING else that reads environment vars ───
env_path = pathlib.Path(__file__).parent / ".env"
if not env_path.exists():
    env_path = pathlib.Path(__file__).parent.parent / ".env"

if env_path.exists():
    logging.basicConfig(level=logging.INFO)
    logging.getLogger(__name__).info(f"Loading .env from {env_path}")
    load_dotenv(dotenv_path=env_path)
else:
    logging.basicConfig(level=logging.WARNING)
    logging.getLogger(__name__).warning(".env not found; expecting system env vars")

# ─── 2) Now safe to import modules that use DATABASE_URL ➔ app.database ───
from fastapi import FastAPI, Request, status, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from app.database import engine, SessionLocal
from app import models
from app.routes import auth, clearance, membership, events, announcements, officers, analytics, chat, cash_payments, toggle_evaluation

# ─── 3) Validate required env vars (optional but recommended) ───
required_env_vars = [
    'CF_ACCESS_KEY_ID',
    'CF_SECRET_ACCESS_KEY',
    'CLOUDFLARE_R2_BUCKET',
    'CLOUDFLARE_R2_ENDPOINT',
    'DATABASE_URL',
]
missing = [v for v in required_env_vars if not os.getenv(v)]
if missing:
    raise RuntimeError(f"Missing required environment variables: {', '.join(missing)}")

# ─── 4) Create and configure FastAPI ───
logger = logging.getLogger(__name__)
app = FastAPI(title="SPECS Nexus API")

# Add CORS middleware BEFORE routers
# Allow localhost for development and Vercel domain for production
allowed_origins = [
    "http://localhost:3000",
    "http://localhost:3001",
    "http://127.0.0.1:3000",
    os.getenv("FRONTEND_URL", "https://specs-nexus-front.vercel.app/"),
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["*"],
    expose_headers=["*"],
)

# ─── 5) Add exception handlers to ensure CORS headers are always included ───
# Dynamic CORS headers based on request origin
def get_cors_headers(origin: str = None):
    allowed = [
        "http://localhost:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3000",
        os.getenv("FRONTEND_URL", "https://specs-nexus.vercel.app"),
    ]
    return {
        "Access-Control-Allow-Origin": origin if origin in allowed else allowed[-1],
        "Access-Control-Allow-Credentials": "true",
        "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS, PATCH",
        "Access-Control-Allow-Headers": "*",
    }

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    origin = request.headers.get("origin")
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
        headers=get_cors_headers(origin)
    )

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    origin = request.headers.get("origin")
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": exc.errors()},
        headers=get_cors_headers(origin)
    )

@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {str(exc)}", exc_info=True)
    origin = request.headers.get("origin")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error"},
        headers=get_cors_headers(origin)
    )

# ─── 6) Add OPTIONS handler for CORS preflight ───
@app.options("/{full_path:path}")
async def options_handler(request: Request, full_path: str):
    origin = request.headers.get("origin")
    return JSONResponse(
        content={},
        headers=get_cors_headers(origin)
    )

# ─── 7) Mount your routers ───
for router in (auth, clearance, membership, events, announcements, officers, analytics, chat, cash_payments, toggle_evaluation):
    app.include_router(router.router)

# ─── 8) Initialize DB ───
try:
    models.Base.metadata.create_all(bind=engine)
    logger.info("Database tables created successfully")
except Exception as e:
    logger.error(f"Error creating database tables: {e}")
    raise

@app.get("/")
def home():
    return {"message": "Welcome to SPECS Nexus API"}
