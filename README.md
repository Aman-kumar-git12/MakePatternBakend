# MakePattern API

The REST backend for MakePattern, a DSA practice tracker: folders of problems, solutions and test cases, spaced-repetition reviews, streaks, LeetCode import and sync, pattern sharing, and optional code execution through Judge0.

Built with **FastAPI** and **MongoDB**. The web app in [`../frontend`](../frontend) is its client.

## Contents

- [Features](#features)
- [Architecture](#architecture)
- [Tech stack](#tech-stack)
- [Getting started](#getting-started)
- [Configuration](#configuration)
- [API reference](#api-reference)
- [Authentication](#authentication)
- [Rate limiting](#rate-limiting)
- [Testing](#testing)
- [Project structure](#project-structure)
- [Deployment](#deployment)
- [Security](#security)
- [Troubleshooting](#troubleshooting)
- [Contributing and license](#contributing-and-license)

## Features

- **Workspace**: nested folders with no depth limit (moves that would create a cycle are rejected), questions, multiple named solutions per question and per-question test cases. Folders and questions can be reordered.
- **Bulk actions** on many questions at once: move, set status, set difficulty, add or remove tags, bookmark, unbookmark, delete.
- **Spaced repetition**: solving a question schedules reviews on the ladder **1 → 3 → 7 → 14 → 30 → 60 → 120 days**. Reviews are rated `again` (back to day 1, status "Needs Revision"), `hard` (repeat the current step), `good` (one step up) or `easy` (two steps up). Reviews done offline are synced in a batch, idempotently.
- **Progress and streaks**: an activity log of solves, reviews and attempts, a daily heatmap over up to 730 days, and current/longest streaks computed in the user's timezone (sent in the `X-Timezone` header).
- **LeetCode integration** through LeetCode's public GraphQL endpoint, with an in-memory cache: look up a problem by URL, slug or number, search, import with title, difficulty, tags, statement and example test cases, refresh a statement, read the daily challenge and a public profile, and sync a user's recent accepted submissions.
- **Starter curricula**: "Core Interview Patterns" and "Beginner Foundations", imported without any network calls.
- **Sharing**: publish a folder as an immutable public snapshot behind a share link, toggle or regenerate the link, and let other users copy ("fork") a shared pattern into their own workspace.
- **Soft delete**: deleted questions and folders go to a trash, can be restored for 30 days, and are then removed automatically by a MongoDB TTL index.
- **Account management**: profile, preferences, change password, sign out of every session, full JSON export and import, and account deletion.
- **Code execution**: optional Judge0 integration for running C++ and Java (Python and JavaScript run in the browser and need no server).
- **Complexity estimate**: a built-in static estimate of a solution's time and space complexity.

## Architecture

```
            HTTPS (Bearer JWT)
  Web app ─────────────────────► FastAPI app (app/main.py)
                                   │  CORS · security headers · JSON 500 handler
                                   ▼
                              Routers (app/routers)      request validation via Pydantic schemas (app/schemas)
                                   │
                                   ▼
                              Services (app/services)    business logic: tracking/SRS, sharing, trash,
                                   │                     LeetCode client, Judge0 client, rate limiter
                                   ▼
                              app/db.py ──► MongoDB      single source of truth
                                   │
                     ┌─────────────┴─────────────┐
                     ▼                           ▼
          leetcode.com/graphql          Judge0 (optional)
```

- **Routers** stay thin: they authenticate, check ownership and call services.
- **Services** hold the logic and keep multi-document work batched (`repo.py` avoids N+1 queries).
- **`app/db.py`** owns the MongoDB client, creates indexes on startup and provides shared helpers (ids, timestamps). Tests swap the database for an in-memory one through `set_database_override`.
- On startup the app connects, creates indexes and runs idempotent data migrations. If MongoDB is unreachable it keeps serving and endpoints return `503` until the database is back.

**MongoDB collections**

| Collection | Contents |
|---|---|
| `users` | Accounts, hashed passwords, `token_version`, preferences, share records |
| `folders` | Folder tree (`parent_id`, `position`) |
| `questions` | Problems, status, difficulty, tags, notes, review schedule |
| `solutions` | Named solutions with code, language and complexity |
| `test_cases` | Inputs and expected outputs per question |
| `bookmarks` | One document per bookmarked question |
| `activity` | Solve / review / attempt events used for streaks and the heatmap |
| `share_snapshots` | Immutable public copies of shared folders |
| `trash` | Soft-deleted items, expired by a TTL index after 30 days |

## Tech stack

| Area | Choice |
|---|---|
| Language | Python 3.12 (CI version) |
| Framework | FastAPI, Uvicorn |
| Validation and settings | Pydantic v2, pydantic-settings |
| Database | MongoDB through PyMongo (Atlas in production) |
| Auth | PyJWT (HS256), bcrypt |
| HTTP client | httpx (LeetCode, Judge0) |
| Tests | pytest, mongomock |

## Getting started

### Prerequisites

- Python 3.12 (3.10+ should work)
- A MongoDB database: a local one from the repository's `docker-compose.yml`, or a MongoDB Atlas cluster

### Run locally

```bash
# From the repository root: start a local MongoDB (optional, needs Docker)
docker compose up -d

cd backend
python3 -m venv venv
source venv/bin/activate            # Windows: venv\Scripts\activate
pip install -r requirements-dev.txt
cp .env.example .env                # then edit .env
python run.py
```

For the local database, set `MONGODB_URI=mongodb://localhost:27017` in `.env`.

The API is now at http://localhost:8000/api. In development, interactive docs are at http://localhost:8000/docs. Check it with:

```bash
curl http://localhost:8000/api/health
# {"status":"ok","version":"2.0.0"}
```

`run.py` reloads on code changes outside production. Never point a development `.env` at the production database.

## Configuration

Settings are read from environment variables, or from a `.env` file in `backend/` (see [`.env.example`](.env.example)).

| Variable | Default | Required | Description |
|---|---|---|---|
| `MONGODB_URI` | — | **Yes in production** | MongoDB connection string. `MONGODB_URL` is accepted as an alias. |
| `MONGODB_DB_NAME` | `dsa_tracker` | No | Database name. |
| `JWT_SECRET` | an insecure development value | **Yes in production** | Secret used to sign tokens. In production it must be at least 32 characters and not a known placeholder, or startup fails. |
| `ENVIRONMENT` | `development` | No | `development` or `production` (`prod` and `staging` count as production). Detected as `production` automatically on Render, Vercel, Fly.io and Railway. |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `43200` (30 days) | No | Token lifetime. Keep it equal to the 30-day session cookie the web app sets. |
| `ALGORITHM` | `HS256` | No | JWT signing algorithm. |
| `HOST` / `PORT` | `0.0.0.0` / `8000` | No | Where `run.py` listens. |
| `CLIENT_URL` | `https://make-pattern-dev.vercel.app` | No | The web app's origin, allowed by CORS. |
| `CORS_ORIGINS` | empty | No | Extra allowed origins, comma-separated (`*` is ignored). |
| `CORS_ORIGIN_REGEX` | `^https://make-pattern[a-z0-9\-]*\.vercel\.app$` | No | Regex for this project's preview deployments. In development, `localhost` and `127.0.0.1` on any port are also allowed. |
| `LEETCODE_GRAPHQL_URL` | `https://leetcode.com/graphql` | No | LeetCode GraphQL endpoint. |
| `JUDGE0_URL` | — | No | Enables C++/Java execution when set. |
| `JUDGE0_API_KEY` | — | No | RapidAPI key, or the `X-Auth-Token` of a self-hosted Judge0. |
| `JUDGE0_API_HOST` | — | No | RapidAPI host, for example `judge0-ce.p.rapidapi.com`. |

Generate a strong secret with:

```bash
python -c 'import secrets; print(secrets.token_urlsafe(48))'
```

## API reference

All routes are under `/api`. "Auth" means a `Authorization: Bearer <token>` header is required; every authenticated route only ever reads or writes the caller's own data. Request and response models are defined in [`app/schemas`](app/schemas). In development the full OpenAPI spec is at `/openapi.json` and the docs at `/docs`; both are disabled in production.

### System

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/api/health` | No | `200 {"status":"ok"}`, or `503 {"status":"degraded"}` when MongoDB is unreachable |
| GET | `/` | No | Liveness message |

### Auth and account (`/api/auth`)

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/register` | No | Create an account and return a token |
| POST | `/login` | No | Sign in; an unknown email creates a new account (see [Authentication](#authentication)) |
| GET | `/me` | Yes | Current user |
| PUT | `/me` | Yes | Update profile (name, LeetCode username) |
| POST | `/change-password` | Yes | Change password; returns a fresh token and signs out every other session |
| POST | `/logout-all` | Yes | Invalidate every issued token |
| POST | `/delete-account` | Yes | Delete the account and all its data (password required) |
| GET | `/export` | Yes | Export all data as JSON |
| POST | `/import` | Yes | Import a JSON export as new items (max 10 MB) |
| GET | `/preferences` | Yes | Read preferences |
| PUT | `/preferences` | Yes | Update preferences |

### Folders (`/api/folders`)

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/tree` | Yes | Full folder tree with question counts and progress |
| POST | `/` | Yes | Create a folder |
| PUT | `/{folder_id}` | Yes | Rename or edit a folder |
| POST | `/{folder_id}/move` | Yes | Move under another parent (cycles rejected) |
| POST | `/reorder` | Yes | Reorder sibling folders |
| DELETE | `/{folder_id}` | Yes | Move a folder and its contents to the trash |
| GET | `/{folder_id}/share` | Yes | Share settings |
| POST | `/{folder_id}/share` | Yes | Create or enable a share link |
| PUT / PATCH | `/{folder_id}/share` | Yes | Turn sharing on or off |
| POST | `/{folder_id}/share/revoke` | Yes | Revoke the link and issue a new one |
| DELETE | `/{folder_id}/share` | Yes | Disable sharing |

### Questions (`/api/questions`)

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/` | Yes | List questions; filters `folder_id`, `difficulty`, `status`, `search` |
| GET | `/random` | Yes | Random practice picks (`count`, `only_revision`, `pool`, `status`, `difficulty`) |
| GET | `/{question_id}` | Yes | Question with solutions and test cases |
| POST | `/` | Yes | Create a question |
| PUT | `/{question_id}` | Yes | Update a question (status changes update the review schedule) |
| POST | `/{question_id}/attempt` | Yes | Log an attempt and time spent |
| POST | `/{question_id}/move` | Yes | Move to another folder |
| POST | `/reorder` | Yes | Reorder questions |
| POST | `/bulk` | Yes | Bulk action (move, set_status, set_difficulty, add_tags, remove_tags, bookmark, unbookmark, delete) |
| DELETE | `/{question_id}` | Yes | Move to the trash |

### Solutions (`/api/solutions`)

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/question/{question_id}` | Yes | Solutions of a question |
| POST | `/question/{question_id}` | Yes | Add a solution |
| PUT | `/{solution_id}` | Yes | Update a solution |
| POST | `/{solution_id}/analyze` | Yes | Re-run the complexity estimate |
| DELETE | `/{solution_id}` | Yes | Delete a solution |
| POST | `/analyze-complexity` | Yes | Estimate the complexity of arbitrary code |

### Test cases (`/api/test-cases`)

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/question/{question_id}` | Yes | Test cases of a question |
| POST | `/question/{question_id}` | Yes | Add a test case |
| PUT | `/{test_case_id}` | Yes | Update a test case |
| DELETE | `/{test_case_id}` | Yes | Delete a test case |

### Reviews (`/api/reviews`)

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/due` | Yes | Reviews due today and in the coming week |
| POST | `/{question_id}` | Yes | Rate a review: `again`, `hard`, `good` or `easy` |
| POST | `/batch` | Yes | Sync reviews done offline (idempotent per client id) |

### Progress, bookmarks and search

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/api/progress/summary` | Yes | Totals, per-status and per-difficulty counts, streaks |
| GET | `/api/progress/activity` | Yes | Daily activity heatmap (`days`, 7–730, default 365) |
| GET | `/api/bookmarks/` | Yes | Bookmarked questions |
| POST | `/api/bookmarks/{question_id}/toggle` | Yes | Bookmark or unbookmark |
| GET | `/api/search/?q=` | Yes | Search questions (title, statement, notes, tags, LeetCode id) and folders |

### LeetCode (`/api/leetcode`)

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/problem?q=` | Yes | Look up a problem by URL, slug or number |
| GET | `/search?q=&limit=` | Yes | Search LeetCode problems (shows which are already tracked) |
| POST | `/import` | Yes | Import a problem with its statement and example test cases |
| POST | `/refresh/{question_id}` | Yes | Refresh a tracked problem's statement |
| GET | `/daily` | Yes | Today's daily challenge |
| GET | `/profile/{username}` | Yes | Public profile stats |
| POST | `/sync` | Yes | Mark recently accepted submissions as solved (last 20) |

### Curricula, trash, sharing and code execution

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/api/curricula` | Yes | Available starter curricula |
| POST | `/api/curricula/{curriculum_id}/import` | Yes | Import a curriculum into the workspace |
| GET | `/api/trash` | Yes | Trashed items |
| POST | `/api/trash/{trash_id}/restore` | Yes | Restore an item |
| DELETE | `/api/trash/{trash_id}` | Yes | Delete an item permanently |
| DELETE | `/api/trash` | Yes | Empty the trash |
| GET | `/api/shared/{share_id}` | **No** | Public snapshot of a shared pattern |
| GET | `/api/shared/{share_id}/questions/{question_id}` | **No** | One question from a public snapshot |
| POST | `/api/shared/{share_id}/fork` | Yes | Copy a shared pattern into my workspace |
| GET | `/api/run/config` | Yes | Whether Judge0 is enabled and which languages can run |
| POST | `/api/run/judge0` | Yes | Run code on Judge0 (`cpp`, `java`, `python`, `javascript`) |

Errors use FastAPI's format, `{"detail": "..."}`. Unhandled errors return `500 {"detail": "Internal server error. Please try again."}` with CORS headers, so the browser sees a server error instead of a network failure.

## Authentication

- **Tokens**: `POST /api/auth/login` or `/register` returns `{"access_token", "token_type": "bearer", "user"}`. Send the token as `Authorization: Bearer <token>`. Tokens are HS256 JWTs valid for 30 days by default.
- **Any email works, by design.** Emails are never verified. Logging in with an email that has no account creates one (the password must be at least 6 characters). This keeps sign-up frictionless and is intentional.
- **Passwords** are hashed with bcrypt. They must be 6 characters or longer and at most 72 bytes; longer passwords are rejected, never silently truncated.
- **Sign out everywhere**: every token carries the user's `token_version`. Changing the password or calling `/logout-all` increments it, which invalidates every token issued before.
- **CORS** allows `Authorization`, `Content-Type` and `X-Timezone` headers with credentials disabled, because auth uses Bearer tokens instead of cookies.

## Rate limiting

An in-process sliding-window limiter ([`app/services/ratelimit.py`](app/services/ratelimit.py)) returns `429` with a `Retry-After` header. It is per instance, which suits a single server.

| Action | Limit |
|---|---|
| Login | 30 per 5 min per IP; 10 per 5 min per IP and email; 30 per 15 min per email |
| Registration (including auto-created accounts) | 10 per hour per IP |
| Change password / delete account | 10 per hour per user |
| JSON import | 10 per hour per user |
| LeetCode endpoints | 60 per minute per user |
| Fork a shared pattern | 20 per hour per user |
| Judge0 runs | 30 per minute per user, one run at a time per user, 4 at once server-wide |

The client IP is the right-most `X-Forwarded-For` entry, which the hosting proxy (Render) appends; anything left of it is client-supplied and ignored.

## Testing

```bash
cd backend
source venv/bin/activate
pip install -r requirements-dev.txt
python -m pytest -q
```

Tests run against an in-memory MongoDB ([mongomock](https://github.com/mongomock/mongomock)) and never touch a real database. `tests/conftest.py` points `MONGODB_URI` at an invalid host so an accidental real connection fails, and resets the rate limiter for every test.

| File | Covers |
|---|---|
| `test_api.py` | Auth, folders, questions, solutions, reviews, progress, sharing and the main API flows |
| `test_bugfixes.py` | Regression tests for fixed bugs |
| `test_bulk_trash_import.py` | Bulk actions, trash and restore, JSON import |
| `test_curricula.py` | Curriculum listing and import |
| `test_leetcode_parse.py` | LeetCode URL/slug parsing and statement/example extraction |
| `test_legacy_data.py` | Documents written by older versions |
| `test_run.py` | Judge0 configuration, limits and responses |

CI ([`.github/workflows/ci.yml`](../.github/workflows/ci.yml)) runs the suite on every push; it needs no secrets or network.

## Project structure

```
backend/
├── app/
│   ├── main.py            # App factory: middleware, CORS, routers, startup (indexes, migrations)
│   ├── config.py          # Settings from env vars, production safety checks
│   ├── db.py              # MongoDB client, indexes, shared helpers
│   ├── routers/           # One module per resource (HTTP layer)
│   │   ├── auth.py  folders.py  questions.py  solutions.py  test_cases.py
│   │   ├── reviews.py  progress.py  bookmarks.py  search.py  leetcode.py
│   │   └── curricula.py  trash.py  shared.py  run.py
│   ├── schemas/           # Pydantic request/response models
│   └── services/          # Business logic
│       ├── tracking.py        # Spaced repetition, activity log, streaks, timezones
│       ├── leetcode.py        # LeetCode GraphQL client with TTL cache
│       ├── leetcode_parse.py  # URL/slug parsing, statement and example extraction
│       ├── share_service.py   # Share links, public snapshots, forking
│       ├── trash.py           # Soft delete and restore
│       ├── importer.py        # JSON export import
│       ├── curricula.py       # Built-in starter curricula
│       ├── judge0.py          # Judge0 client
│       ├── complexity_service.py  # Static complexity estimate
│       ├── folder_service.py  # Folder tree building and move validation
│       ├── repo.py            # Document ↔ response mapping, batched queries
│       ├── ratelimit.py       # In-process rate limiter
│       └── security.py        # Password hashing, JWT
├── tests/                 # pytest suite (mongomock)
├── run.py                 # Local entry point (uvicorn)
├── requirements.txt       # Runtime dependencies
├── requirements-dev.txt   # + test dependencies
├── pyproject.toml         # Project metadata and pytest settings
└── .env.example           # Configuration template
```

## Deployment

The backend is deployed on **Render** as a web service:

| Setting | Value |
|---|---|
| Root directory | `backend` |
| Build command | `pip install -r requirements.txt` |
| Start command | `uvicorn app.main:app --host 0.0.0.0 --port $PORT` |
| Health check path | `/api/health` |

Required environment variables in production: `MONGODB_URI` and `JWT_SECRET`. Set `CLIENT_URL` (and `CORS_ORIGINS` if needed) to the web app's origin. Add the `JUDGE0_*` variables to enable C++/Java execution.

`ENVIRONMENT` is detected as `production` on Render automatically, which turns on the secret checks and disables `/docs`. The rate limiter is in memory, so run one instance, or replace it with a shared store before scaling out.

## Security

- No credentials are stored in code; `.env` files are git-ignored. Rotate any secret that has ever been committed.
- Production startup refuses weak or placeholder `JWT_SECRET` values and a missing `MONGODB_URI`.
- Every query for user data is scoped to the authenticated user's id.
- Responses carry `X-Content-Type-Options: nosniff`, `Referrer-Policy: strict-origin-when-cross-origin` and `X-Frame-Options: DENY`.
- Shared patterns are served from immutable snapshots, so later edits or deletions in the owner's workspace never leak through a public link.
- Input sizes are bounded by Pydantic models (for example, Judge0 code is limited to 100,000 characters and imports to 10 MB).

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| Startup fails with `JWT_SECRET must be set to a strong random value` | Running in production (or on Render/Vercel/Fly/Railway) without a proper secret. Set a 32+ character `JWT_SECRET`. |
| Startup fails with `MONGODB_URI must be set in production` | Set `MONGODB_URI`. |
| Every request returns `503 Database unavailable` | MongoDB is unreachable: check the URI, that the database is running, and (for Atlas) the IP access list. `GET /api/health` reports `degraded` meanwhile. |
| The browser reports a CORS error | The web app's origin is not allowed. Set `CLIENT_URL` or add it to `CORS_ORIGINS`. |
| `/docs` returns 404 | Docs are disabled in production; run with `ENVIRONMENT=development`. |
| `429 Too many attempts` | A rate limit was hit; wait for the time in `Retry-After`. |
| C++/Java runs are unavailable | Set `JUDGE0_URL` (and the key/host). `GET /api/run/config` shows whether Judge0 is enabled. |

## Contributing and license

See [CONTRIBUTING.md](../CONTRIBUTING.md) for the development workflow. Released under the [MIT License](../LICENSE).
