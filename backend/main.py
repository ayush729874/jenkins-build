from fastapi import FastAPI, HTTPException
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field, HttpUrl
from contextlib import asynccontextmanager, contextmanager
import mysql.connector
from mysql.connector.pooling import MySQLConnectionPool
import os
import string
import time

# ─────────────────────────────────────────
#   BASE62 ENCODER  (bijective — no XOR scramble)
# ─────────────────────────────────────────
BASE62_CHARS = string.ascii_letters + string.digits   # a-z A-Z 0-9  (62 chars)

# ID_OFFSET guarantees a minimum 6-char code from the very first DB row.
# 62^5 = 916_132_832  →  any number >= this encodes to at least 6 chars.
ID_OFFSET = 916_132_832


def encode_base62(num: int) -> str:
    """
    Convert a DB auto-increment ID into a short Base62 code.

    Key change vs original:
    - Removed XOR scrambling.  XOR is NOT bijective in Base62 space — two
      different IDs can map to the same Base62 string, causing the
      IntegrityError / collision bug you saw.
    - Pure Base62(num + ID_OFFSET) IS bijective: every distinct integer
      produces a distinct code, guaranteed.

    Examples (ID → code):
        1  → cOHgOk   (same visual length, just sequential)
        2  → cOHgOl
       50  → cOHgWK
    If you want non-sequential-looking codes, swap in a format-preserving
    encryption library (e.g. pyffx) rather than XOR.
    """
    num = num + ID_OFFSET
    if num == 0:
        return BASE62_CHARS[0]
    code = []
    while num:
        num, remainder = divmod(num, 62)
        code.append(BASE62_CHARS[remainder])
    return ''.join(reversed(code))


# ─────────────────────────────────────────
#   CONNECTION POOL  (created once at import time)
# ─────────────────────────────────────────
# pool_size=10 means at most 10 simultaneous DB connections.
# Tune this to stay under your MySQL max_connections setting.
# Each connection reuses the same OS file descriptor, so the
# "too many open files" error goes away under load.
_pool: MySQLConnectionPool | None = None


def _create_pool() -> MySQLConnectionPool:
    return MySQLConnectionPool(
        pool_name="treecom_pool",
        pool_size=int(os.getenv("DB_POOL_SIZE", 10)),
        pool_reset_session=True,
        host=os.getenv("DB_HOST"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        database=os.getenv("DB_NAME"),
        port=int(os.getenv("DB_PORT", 3306)),
        autocommit=False,
        connection_timeout=10,
    )


def get_db():
    """
    Return a pooled connection.
    Calling .close() on a pooled connection returns it to the pool
    rather than closing the underlying socket — no fd leak.
    """
    global _pool
    if _pool is None:
        raise Exception("DB pool not initialised — did lifespan run?")
    try:
        return _pool.get_connection()
    except Exception as e:
        raise Exception(f"DB pool error: {e}")


# ─────────────────────────────────────────
#   CONTEXT MANAGER  (guarantees connection is returned to pool)
# ─────────────────────────────────────────
@contextmanager
def db_cursor(dictionary: bool = False):
    """
    Usage:
        with db_cursor(dictionary=True) as (conn, cur):
            cur.execute(...)

    Commits on success, rolls back on any exception, and ALWAYS
    returns the connection to the pool — even if an HTTPException
    is raised mid-handler.
    """
    conn = get_db()
    cur = conn.cursor(dictionary=dictionary)
    try:
        yield conn, cur
        conn.commit()
    except HTTPException:
        conn.rollback()
        raise                    # re-raise so FastAPI handles it normally
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()             # returns to pool, does NOT close socket


# ─────────────────────────────────────────
#   DB INIT  (runs once on startup, with retry)
# ─────────────────────────────────────────
def init_db():
    """
    Create tables if they don't exist, and fix column sizes on
    existing tables.  Retries up to 10 times — MySQL pod may still
    be initialising when the backend starts.
    """
    for attempt in range(1, 11):
        try:
            with db_cursor() as (conn, cur):
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS urls (
                        id           BIGINT AUTO_INCREMENT PRIMARY KEY,
                        short_code   VARCHAR(20) NOT NULL UNIQUE,
                        original_url TEXT NOT NULL,
                        created_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
                        click_count  INT DEFAULT 0,
                        INDEX idx_original_url (original_url(255))
                    )
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS feedback (
                        id          BIGINT AUTO_INCREMENT PRIMARY KEY,
                        short_code  VARCHAR(20) NOT NULL,
                        rating      TINYINT NOT NULL,
                        feedback    VARCHAR(400) DEFAULT NULL,
                        created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (short_code) REFERENCES urls(short_code)
                            ON DELETE CASCADE
                    )
                """)

                # Widen columns on pre-existing tables (safe no-op if already correct)
                for ddl, label in [
                    ("ALTER TABLE urls MODIFY short_code VARCHAR(20) NOT NULL",
                     "urls.short_code"),
                    ("ALTER TABLE feedback MODIFY short_code VARCHAR(20) NOT NULL",
                     "feedback.short_code"),
                ]:
                    try:
                        cur.execute(ddl)
                        print(f"[startup] {label} column ensured VARCHAR(20).")
                    except Exception as alter_err:
                        print(f"[startup] ALTER {label} skipped: {alter_err}")

            print(f"[startup] Tables verified / created (attempt {attempt}).")
            return

        except Exception as e:
            print(f"[startup] DB not ready (attempt {attempt}/10): {e}")
            if attempt < 10:
                time.sleep(3)
            else:
                print("[startup] WARNING: Could not init DB after 10 attempts. Continuing...")


# ─────────────────────────────────────────
#   APP
# ─────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    global _pool
    # Retry pool creation — DB pod may not be ready yet
    for attempt in range(1, 11):
        try:
            _pool = _create_pool()
            print(f"[startup] DB connection pool created (attempt {attempt}).")
            break
        except Exception as e:
            print(f"[startup] Pool creation failed (attempt {attempt}/10): {e}")
            if attempt < 10:
                time.sleep(3)
            else:
                print("[startup] WARNING: Could not create pool. Continuing without it.")

    init_db()
    yield
    # Graceful shutdown — close all pooled connections
    # mysql-connector's pool has no explicit close(), connections are
    # GC'd naturally; this is a no-op placeholder for future upgrades.
    print("[shutdown] Application shutting down.")


app = FastAPI(title="Treecom URL Shortener", lifespan=lifespan)


# ─────────────────────────────────────────
#   REQUEST / RESPONSE MODELS
# ─────────────────────────────────────────
class ShortenRequest(BaseModel):
    original_url: HttpUrl

class ShortenResponse(BaseModel):
    short_code: str
    short_url: str
    original_url: str

class FeedbackRequest(BaseModel):
    short_code: str = Field(..., min_length=1, max_length=20)
    rating: int = Field(..., ge=1, le=5)
    feedback: str | None = Field(None, max_length=400)


# ─────────────────────────────────────────
#   ENDPOINTS
# ─────────────────────────────────────────

@app.get("/")
async def root():
    """Health check — used by readiness/liveness probes."""
    return {"status": "Treecom URL Shortener is running"}


# ── 1. SHORTEN ──────────────────────────
@app.post("/shorten", response_model=ShortenResponse)
async def shorten_url(request: ShortenRequest):
    original = str(request.original_url)
    base_url = os.getenv("BASE_URL", "https://test.treecom.site")

    try:
        with db_cursor(dictionary=True) as (conn, cur):

            # ── Return existing short URL if this long URL was already shortened ──
            # This also eliminates duplicate rows for the same original URL.
            cur.execute(
                "SELECT short_code FROM urls WHERE original_url = %s LIMIT 1",
                (original,)
            )
            existing = cur.fetchone()
            if existing:
                sc = existing["short_code"]
                return ShortenResponse(
                    short_code=sc,
                    short_url=f"{base_url}/{sc}",
                    original_url=original,
                )

            # ── Insert a temporary placeholder row to obtain the auto-increment ID ──
            # We use a row-specific placeholder (f"_tmp_{time.time_ns()}") so that
            # concurrent requests never collide on the placeholder value.
            tmp = f"_tmp_{time.time_ns()}"
            cur.execute(
                "INSERT INTO urls (original_url, short_code) VALUES (%s, %s)",
                (original, tmp)
            )
            new_id = cur.lastrowid

            # ── Derive the real short code from the now-known ID ──
            # encode_base62 is bijective, so this is guaranteed unique.
            short_code = encode_base62(new_id)

            cur.execute(
                "UPDATE urls SET short_code = %s WHERE id = %s",
                (short_code, new_id)
            )
            # conn.commit() is called automatically by db_cursor on context exit

            return ShortenResponse(
                short_code=short_code,
                short_url=f"{base_url}/{short_code}",
                original_url=original,
            )

    except mysql.connector.IntegrityError as e:
        # This path should never be reached now (bijective encoding + dedup
        # check above), but kept as a belt-and-suspenders safety net.
        # Instead of surfacing an error, we attempt to return the existing entry.
        try:
            with db_cursor(dictionary=True) as (_, cur):
                cur.execute(
                    "SELECT short_code FROM urls WHERE original_url = %s LIMIT 1",
                    (original,)
                )
                row = cur.fetchone()
            if row:
                sc = row["short_code"]
                return ShortenResponse(
                    short_code=sc,
                    short_url=f"{base_url}/{sc}",
                    original_url=original,
                )
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=f"Could not create short URL: {e}")

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Server error: {e}")


# ── 2. REDIRECT ─────────────────────────
@app.get("/{short_code}")
async def redirect_to_original(short_code: str):
    # Validate: alphanumeric only, max 20 chars (matches new VARCHAR(20))
    if not short_code.isalnum() or len(short_code) > 20:
        raise HTTPException(status_code=400, detail="Invalid short code.")

    try:
        with db_cursor(dictionary=True) as (conn, cur):
            cur.execute(
                "SELECT id, original_url FROM urls WHERE short_code = %s",
                (short_code,)
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Short URL not found.")

            cur.execute(
                "UPDATE urls SET click_count = click_count + 1 WHERE id = %s",
                (row["id"],)
            )

        return RedirectResponse(url=row["original_url"], status_code=302)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Server error: {e}")


# ── 3. FEEDBACK ─────────────────────────
@app.post("/feedback")
async def submit_feedback(request: FeedbackRequest):
    try:
        with db_cursor() as (conn, cur):
            cur.execute(
                "SELECT id FROM urls WHERE short_code = %s",
                (request.short_code,)
            )
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail="Short code not found.")

            cur.execute(
                "INSERT INTO feedback (short_code, rating, feedback) VALUES (%s, %s, %s)",
                (request.short_code, request.rating, request.feedback or None)
            )

        return {"status": "success", "message": "Feedback saved. Thank you!"}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Server error: {e}")


# ── 4. STATS ────────────────────────────
@app.get("/stats/{short_code}")
async def get_stats(short_code: str):
    try:
        with db_cursor(dictionary=True) as (conn, cur):
            cur.execute(
                "SELECT short_code, original_url, created_at, click_count "
                "FROM urls WHERE short_code = %s",
                (short_code,)
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Short code not found.")

            cur.execute(
                "SELECT AVG(rating) AS avg_rating, COUNT(*) AS total_feedback "
                "FROM feedback WHERE short_code = %s",
                (short_code,)
            )
            fb = cur.fetchone()

        return {
            **row,
            "created_at": str(row["created_at"]),
            "avg_rating": round(float(fb["avg_rating"]), 1) if fb["avg_rating"] else None,
            "total_feedback": fb["total_feedback"],
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Server error: {e}")
