from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from app.database import engine, Base, SessionLocal
from app.config import settings
from app.routers import auth, folders, questions, solutions, bookmarks, progress, search, test_cases
from app.services.seed_service import seed_demo_data
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

    # Seed demo curriculum only in development when database has no users
    if getattr(settings, "ENVIRONMENT", "production") == "development":
        db = SessionLocal()
        try:
            from app.models.user import User
            user_count = db.query(User).count()
            if user_count == 0:
                logger.info("No users found in development database. Seeding demo user and patterns...")
                seed_demo_data(db)
                logger.info("Demo data seeded successfully.")
            else:
                logger.info(f"Database has {user_count} user(s). Demo seeding skipped.")
        except Exception as e:
            logger.error(f"Development demo seeding failed: {e}", exc_info=True)
        finally:
            db.close()
    else:
        logger.info("Non-development environment: demo seeding disabled.")

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
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
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
