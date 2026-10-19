from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from app.config import settings
import logging

logger = logging.getLogger("dsa_tracker.database")

engine = None
db_url = settings.DATABASE_URL

def init_engine(url: str):
    if "postgresql" in url:
        eng = create_engine(url, pool_pre_ping=True)
        # Test connection immediately
        with eng.connect():
            logger.info("Successfully connected to PostgreSQL database.")
        return eng
    elif "sqlite" in url:
        logger.info(f"Using SQLite database engine at {url}")
        return create_engine(url, connect_args={"check_same_thread": False})
    else:
        raise ValueError(
            f"Unsupported database scheme in DATABASE_URL ('{url}'). "
            "Supported schemes are PostgreSQL ('postgresql://...') or SQLite ('sqlite:///...')."
        )

try:
    engine = init_engine(db_url)
except Exception as e:
    logger.warning(
        f"Could not connect to external DATABASE_URL ({e}). "
        "Using local engine with MongoDB Atlas as the primary cloud database."
    )
    db_url = "sqlite:///./dsa_tracker.db"
    engine = create_engine(db_url, connect_args={"check_same_thread": False})

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
