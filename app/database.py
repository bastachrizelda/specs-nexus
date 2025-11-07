import os
import logging
from urllib.parse import urlparse

from dotenv import load_dotenv, find_dotenv

# SQLAlchemy imports
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# Async support (optional)
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession

# load .env: prefer app/.env next to this file, fallback to project .env
env_path = os.path.join(os.path.dirname(__file__), ".env")
if not os.path.exists(env_path):
    env_path = find_dotenv()  # try locating a .env in parent folders
load_dotenv(env_path)

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def resolve_database_url() -> str:
    """
    Resolve the final DATABASE_URL to use.
    Priority:
      1. DATABASE_URL (if it's already a Postgres URL)
      2. DATABASE_URL if it's postgresql+asyncpg:// or postgresql://
      3. Try common fallback env vars: SUPABASE_DB_URL, SUPABASE_DATABASE_URL, POSTGRES_URL
      4. If DATABASE_URL is a MySQL URL and no fallback found -> raise with instructions
      5. If only SUPABASE_URL+SUPABASE_KEY present, raise (cannot derive DB creds from anon/service keys)
    """
    raw = os.getenv("DATABASE_URL")
    if not raw:
        raise ValueError(
            "DATABASE_URL not set. Add DATABASE_URL pointing to your Supabase Postgres connection string."
        )

    raw = raw.strip().strip('"').strip("'")
    # If already a Postgres URL, return
    if raw.startswith(("postgresql://", "postgresql+asyncpg://", "postgres://")):
        return raw

    # If it's MySQL, try common fallbacks
    if raw.startswith("mysql://"):
        logger.warning("Detected MySQL DATABASE_URL in .env; attempting to locate Supabase/Postgres fallback vars.")
        for alt in ("SUPABASE_DB_URL", "SUPABASE_DATABASE_URL", "POSTGRES_URL", "DATABASE_URL_POSTGRES"):
            alt_val = os.getenv(alt)
            if alt_val:
                alt_val = alt_val.strip().strip('"').strip("'")
                logger.info("Using fallback DB URL from env var: %s", alt)
                return alt_val
        # If SUPABASE_URL + SERVICE_ROLE_KEY are present, we still cannot form the DB connection string:
        if os.getenv("SUPABASE_URL") and os.getenv("SUPABASE_SERVICE_ROLE_KEY"):
            raise ValueError(
                "DATABASE_URL is a MySQL URL and no Postgres fallback found. "
                "Supabase anon/service keys (SUPABASE_KEY/SUPABASE_SERVICE_ROLE_KEY) do not contain DB credentials. "
                "Get the Postgres connection string from the Supabase dashboard and set DATABASE_URL to "
                "'postgresql://<user>:<pass>@<host>:5432/<db>' (or 'postgresql+asyncpg://' for async)."
            )
        raise ValueError(
            "DATABASE_URL points to MySQL but no Postgres fallback found. Set DATABASE_URL to your Supabase Postgres string."
        )

    # If it's another scheme, try to normalize postgres:// -> postgresql://
    if raw.startswith("postgres://"):
        return raw.replace("postgres://", "postgresql://", 1)

    # Otherwise, return as-is (may raise later when SQLAlchemy tries to connect)
    return raw


# Retrieve final DATABASE_URL
DATABASE_URL = None
try:
    DATABASE_URL = resolve_database_url()
except Exception as e:
    logger.error(str(e))
    raise

logger.info("Loaded DATABASE_URL from environment (value hidden)")

# Normalize common Postgres scheme (Supabase may give "postgres://")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
    logger.info("Rewrote 'postgres://' -> 'postgresql://' for SQLAlchemy")

# Basic validation (do not log secrets)
try:
    parsed_url = urlparse(DATABASE_URL)
    if not parsed_url.scheme or not parsed_url.hostname or parsed_url.path in ("", "/"):
        raise ValueError("DATABASE_URL missing required parts")
except Exception as e:
    logger.error(f"Invalid DATABASE_URL format: {e}")
    raise

logger.info("Processed DATABASE_URL validated")

# Decide sync vs async engine
use_async = DATABASE_URL.startswith("postgresql+asyncpg://") or os.getenv("DB_ASYNC", "0") == "1"

is_production = os.getenv("ENVIRONMENT") == "production"
engine_kwargs = {"future": True}
if is_production:
    engine_kwargs.update({"pool_recycle": 300, "pool_pre_ping": True})

try:
    if use_async:
        # Async engine & session (requires asyncpg)
        engine = create_async_engine(DATABASE_URL, **engine_kwargs)
        SessionLocal = sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
        logger.info("Using async SQLAlchemy engine (asyncpg)")
    else:
        # Sync engine & session (requires psycopg-binary for Postgres)
        engine = create_engine(DATABASE_URL, **engine_kwargs)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        logger.info("Using sync SQLAlchemy engine")
    Base = declarative_base()
except Exception as e:
    logger.error(f"Error initializing database: {e}")
    raise
