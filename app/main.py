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
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.database import engine, SessionLocal
from app import models
from app.routes import auth, clearance, membership, events, announcements, officers, analytics, chat

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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── 5) Mount your routers ───
for router in (auth, clearance, membership, events, announcements, officers, analytics, chat):
    app.include_router(router.router)

# ─── 6) Initialize DB ───
try:
    models.Base.metadata.create_all(bind=engine)
    logger.info("Database tables created successfully")
except Exception as e:
    logger.error(f"Error creating database tables: {e}")
    raise

@app.get("/")
def home():
    return {"message": "Welcome to SPECS Nexus API"}
