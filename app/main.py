from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from app.database import engine, Base, SessionLocal
from app.config import settings
from app.mongodb import init_mongodb
from app.routers import auth, folders, questions, solutions, bookmarks, progress, search, test_cases, shared
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("dsa_tracker")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize database tables
    logger.info("Initializing database schema...")
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("Database schema initialized successfully.")
    except Exception as e:
        logger.critical(f"Database schema initialization failed: {e}", exc_info=True)
        raise

    # Initialize MongoDB connection and indexes
    try:
        init_mongodb()
        # Automatically sync existing SQLite users to MongoDB
        from app.models.user import User as SqlUser
        from app.mongodb import sync_all_sqlite_users_to_mongo
        db = SessionLocal()
        try:
            sql_users = db.query(SqlUser).all()
            sync_all_sqlite_users_to_mongo(sql_users)
            logger.info(f"Successfully verified/synced {len(sql_users)} users to MongoDB.")
        finally:
            db.close()
    except Exception as e:
        logger.warning(f"MongoDB initialization/sync error: {e}")

    yield

app = FastAPI(
    title="DSA Learning Tracker API",
    description="Backend API for DSA Learning Tracker with recursive folders, notes, Monaco editor solutions, and bookmarks",
    version="1.0.0",
    lifespan=lifespan
)

# Configure CORS strictly to permitted frontend origins (no wildcard with credentials)
raw_origins = [settings.CLIENT_URL]
if hasattr(settings, "CORS_ORIGINS") and settings.CORS_ORIGINS:
    raw_origins.extend([o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()])

# Filter unique valid origins and strictly exclude "*"
allowed_origins = sorted(list({origin for origin in raw_origins if origin and origin != "*"}))
logger.info(f"Configured CORS allowed origins: {allowed_origins}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:[0-9]+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register Routers
app.include_router(auth.router, prefix="/api")
app.include_router(folders.router, prefix="/api")
app.include_router(questions.router, prefix="/api")
app.include_router(solutions.router, prefix="/api")
app.include_router(bookmarks.router, prefix="/api")
app.include_router(progress.router, prefix="/api")
app.include_router(search.router, prefix="/api")
app.include_router(test_cases.router, prefix="/api")
app.include_router(shared.router, prefix="/api")


@app.get("/api/health")
def health_check():
    return {
        "status": "healthy",
        "app": "DSA Learning Tracker API",
        "database": str(engine.url.database or engine.url),
        "version": "1.0.0"
    }

@app.get("/")
def root():
    return {"message": "DSA Learning Tracker API is running. Visit /docs for Swagger documentation."}
