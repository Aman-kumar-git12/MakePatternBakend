import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.db import get_database, init_indexes, now_iso, ping
from app.routers import (
    auth,
    bookmarks,
    curricula,
    folders,
    leetcode,
    progress,
    questions,
    reviews,
    run,
    search,
    shared,
    solutions,
    test_cases,
    trash,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("makepattern")


def run_migrations(db) -> None:
    """Idempotent data fix-ups for documents written by older versions."""
    # Questions already flagged for revision become due in the new review queue.
    res = db.questions.update_many(
        {"status": "Needs Revision", "$or": [{"next_review_at": {"$exists": False}}, {"next_review_at": None}]},
        {"$set": {"next_review_at": now_iso(), "review_step": 0, "review_interval_days": 1}},
    )
    if res.modified_count:
        logger.info("Migrated %d revision questions into the review queue", res.modified_count)


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        db = get_database()
        init_indexes(db)
        run_migrations(db)
        logger.info("MongoDB ready (environment=%s)", settings.ENVIRONMENT)
    except Exception as e:  # keep serving; requests will return 503 until Mongo is reachable
        logger.error("MongoDB initialisation failed: %s", e)
    yield


app = FastAPI(
    title="MakePattern API",
    description="DSA pattern tracker: folders, problems, solutions, spaced repetition and LeetCode sync.",
    version="2.0.0",
    lifespan=lifespan,
    docs_url=None if settings.is_production else "/docs",
    redoc_url=None,
    openapi_url=None if settings.is_production else "/openapi.json",
)

origins = {settings.CLIENT_URL.rstrip("/"), "https://make-pattern-dev.vercel.app"}
origins.update(o.strip().rstrip("/") for o in settings.CORS_ORIGINS.split(",") if o.strip() and o.strip() != "*")
origin_regex = settings.CORS_ORIGIN_REGEX
if not settings.is_production:
    origin_regex = rf"{origin_regex}|^http://(localhost|127\.0\.0\.1)(:[0-9]+)?$"

class CatchUnhandledErrors:
    """Turn unhandled exceptions into a JSON 500 *inside* the CORS middleware. Starlette's own
    500 handler runs outside it, so the browser saw a CORS failure (a network TypeError)
    instead of a server error, and the client couldn't tell the two apart."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        started = False

        async def tracking_send(message):
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, receive, tracking_send)
        except Exception:
            logger.exception("Unhandled error on %s %s", scope.get("method"), scope.get("path"))
            if started:
                raise
            response = JSONResponse(status_code=500, content={"detail": "Internal server error. Please try again."})
            await response(scope, receive, send)


# Added first, so it sits inside CORS (the last middleware added is the outermost).
app.add_middleware(CatchUnhandledErrors)

app.add_middleware(
    CORSMiddleware,
    allow_origins=sorted(o for o in origins if o),
    allow_origin_regex=origin_regex,
    allow_credentials=False,  # auth uses Bearer tokens, not cookies
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Timezone"],
    max_age=600,
)


@app.middleware("http")
async def security_headers(request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("X-Frame-Options", "DENY")
    return response


for r in (auth, folders, questions, solutions, bookmarks, progress, search, test_cases, shared, reviews, leetcode, curricula, run, trash):
    app.include_router(r.router, prefix="/api")


@app.get("/api/health")
def health_check():
    ok = ping()
    return JSONResponse(status_code=200 if ok else 503, content={"status": "ok" if ok else "degraded", "version": app.version})


@app.get("/")
def root():
    return {"message": "MakePattern API is running."}
