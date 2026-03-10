from fastapi import FastAPI, HTTPException
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field, HttpUrl
from contextlib import asynccontextmanager
import mysql.connector
import os
import string
import time
import uuid

# ─────────────────────────────────────────
#   BASE62 ENCODER
# ─────────────────────────────────────────
BASE62_CHARS = string.ascii_letters + string.digits  # a-z A-Z 0-9  (62 chars)


# ID_OFFSET ensures minimum 6 chars from the very first DB record
XOR_KEY   = 0x5A4E3C2B
ID_OFFSET = 916_132_832  # = 62^5, first number that produces a 6-char Base62 code

def encode_base62(num: int) -> str:
    """
    Convert a DB auto-increment ID into a 6-char Base62 short code.
    XOR scrambling makes consecutive IDs produce visually different codes.
    e.g.  ID 1  ->  cOHgOk
          ID 2  ->  cOHgOj
          ID 50 ->  cOHgFQ
    """
    num = (num ^ XOR_KEY) + ID_OFFSET
    code = []
    while num:
        num, remainder = divmod(num, 62)
        code.append(BASE62_CHARS[remainder])
    return ''.join(reversed(code))


# ─────────────────────────────────────────
#   DB CONNECTION
# ─────────────────────────────────────────
def get_db():
    """
    Returns a DB connection.
    Raises plain Exception — safe to call both during startup
    and inside request handlers.
    """
    try:
        return mysql.connector.connect(
            host=os.getenv("DB_HOST"),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD"),
            database=os.getenv("DB_NAME"),
            port=int(os.getenv("DB_PORT", 3306)),
            autocommit=False,
            connection_timeout=10,
        )
    except Exception as e:
        raise Exception(f"DB connection error: {e}")


# ─────────────────────────────────────────
#   DB INIT  (runs once on startup, with retry)
# ─────────────────────────────────────────
def init_db():
    """
    Create tables if they don't exist.
    Retries up to 10 times with 3s delay — MySQL pod may still
    be initializing when the backend starts.
    Also runs ALTER TABLE to fix column sizes on existing tables.
    """
    for attempt in range(1, 11):
        try:
            conn = get_db()
            cursor = conn.cursor()

            # Create tables with VARCHAR(20) for short_code
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS urls (
                    id           BIGINT AUTO_INCREMENT PRIMARY KEY,
                    short_code   VARCHAR(20) NOT NULL UNIQUE,
                    original_url TEXT NOT NULL,
                    created_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
                    click_count  INT DEFAULT 0
                )
            """)
            cursor.execute("""
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

            # ALTER existing tables in case they were created with old VARCHAR(10)
            # MySQL ignores this if already the right size — safe to run every time
            try:
                cursor.execute("ALTER TABLE urls MODIFY short_code VARCHAR(20) NOT NULL")
                print("[startup] urls.short_code column updated to VARCHAR(20).")
            except Exception as alter_err:
                print(f"[startup] ALTER urls skipped: {alter_err}")

            try:
                cursor.execute("ALTER TABLE feedback MODIFY short_code VARCHAR(20) NOT NULL")
                print("[startup] feedback.short_code column updated to VARCHAR(20).")
            except Exception as alter_err:
                print(f"[startup] ALTER feedback skipped: {alter_err}")

            conn.commit()
            cursor.close()
            conn.close()
            print(f"[startup] Tables verified / created (attempt {attempt}).")
            return  # success — exit retry loop
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
    init_db()
    yield

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

    try:
        conn = get_db()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    cursor = conn.cursor()
    try:
        # Use a unique temp placeholder per request to avoid collisions
        # under concurrent traffic (uuid4 makes it unique every time)
        tmp_placeholder = f"t{uuid.uuid4().hex[:8]}"  # 9 chars, unique, fits VARCHAR(10)

        cursor.execute(
            "INSERT INTO urls (original_url, short_code) VALUES (%s, %s)",
            (original, tmp_placeholder)
        )
        new_id = cursor.lastrowid

        # Base62-encode the id as the short code
        short_code = encode_base62(new_id)

        # Update row with the real short code
        cursor.execute(
            "UPDATE urls SET short_code = %s WHERE id = %s",
            (short_code, new_id)
        )
        conn.commit()

        base_url = os.getenv("BASE_URL", "https://test.treecom.site")
        return ShortenResponse(
            short_code=short_code,
            short_url=f"{base_url}/{short_code}",
            original_url=original,
        )

    except mysql.connector.IntegrityError as e:
        conn.rollback()
        # This should never happen now with uuid temp placeholders,
        # but kept as a safety net
        raise HTTPException(status_code=409, detail=f"Collision error — please retry. ({e})")
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Server error: {e}")
    finally:
        cursor.close()
        conn.close()


# ── 2. REDIRECT ─────────────────────────
@app.get("/{short_code}")
async def redirect_to_original(short_code: str):
    if not short_code.isalnum() or len(short_code) > 10:
        raise HTTPException(status_code=400, detail="Invalid short code.")

    try:
        conn = get_db()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT id, original_url FROM urls WHERE short_code = %s",
            (short_code,)
        )
        row = cursor.fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="Short URL not found.")

        cursor.execute(
            "UPDATE urls SET click_count = click_count + 1 WHERE id = %s",
            (row["id"],)
        )
        conn.commit()

        return RedirectResponse(url=row["original_url"], status_code=302)

    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Server error: {e}")
    finally:
        cursor.close()
        conn.close()


# ── 3. FEEDBACK ─────────────────────────
@app.post("/feedback")
async def submit_feedback(request: FeedbackRequest):
    try:
        conn = get_db()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT id FROM urls WHERE short_code = %s",
            (request.short_code,)
        )
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="Short code not found.")

        cursor.execute(
            "INSERT INTO feedback (short_code, rating, feedback) VALUES (%s, %s, %s)",
            (request.short_code, request.rating, request.feedback or None)
        )
        conn.commit()
        return {"status": "success", "message": "Feedback saved. Thank you!"}

    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Server error: {e}")
    finally:
        cursor.close()
        conn.close()


# ── 4. STATS ────────────────────────────
@app.get("/stats/{short_code}")
async def get_stats(short_code: str):
    try:
        conn = get_db()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT short_code, original_url, created_at, click_count FROM urls WHERE short_code = %s",
            (short_code,)
        )
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Short code not found.")

        cursor.execute(
            "SELECT AVG(rating) as avg_rating, COUNT(*) as total_feedback FROM feedback WHERE short_code = %s",
            (short_code,)
        )
        fb = cursor.fetchone()

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
    finally:
        cursor.close()
        conn.close()
