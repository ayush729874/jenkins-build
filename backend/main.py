from fastapi import FastAPI, HTTPException
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, HttpUrl
from contextlib import asynccontextmanager
import mysql.connector
import os
import string

# ─────────────────────────────────────────
#   BASE62 ENCODER
# ─────────────────────────────────────────
BASE62_CHARS = string.ascii_letters + string.digits  # a-z A-Z 0-9  (62 chars)

def encode_base62(num: int) -> str:
    """Convert an integer ID to a Base62 short code."""
    if num == 0:
        return BASE62_CHARS[0]
    code = []
    while num:
        num, remainder = divmod(num, 62)
        code.append(BASE62_CHARS[remainder])
    return ''.join(reversed(code))


# ─────────────────────────────────────────
#   DB CONNECTION
# ─────────────────────────────────────────
def get_db():
    try:
        return mysql.connector.connect(
            host=os.getenv("DB_HOST"),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD"),
            database=os.getenv("DB_NAME"),
            port=int(os.getenv("DB_PORT", 3306)),
            autocommit=False,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DB connection error: {e}")


# ─────────────────────────────────────────
#   DB INIT  (runs once on startup)
# ─────────────────────────────────────────
def init_db():
    """Create tables if they don't already exist."""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS urls (
                id           BIGINT AUTO_INCREMENT PRIMARY KEY,
                short_code   VARCHAR(10) NOT NULL UNIQUE,
                original_url TEXT NOT NULL,
                created_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
                click_count  INT DEFAULT 0
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS feedback (
                id          BIGINT AUTO_INCREMENT PRIMARY KEY,
                short_code  VARCHAR(10) NOT NULL,
                rating      TINYINT NOT NULL,
                feedback    VARCHAR(400) DEFAULT NULL,
                created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (short_code) REFERENCES urls(short_code)
                    ON DELETE CASCADE
            )
        """)
        conn.commit()
        print("[startup] Tables verified / created.")
    finally:
        cursor.close()
        conn.close()


# ─────────────────────────────────────────
#   APP
# ─────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield

app = FastAPI(title="Treecom URL Shortener", lifespan=lifespan)

# Serve the frontend HTML from the same directory.
# Place index.html next to main.py and it will be served at "/"
app.mount("/static", StaticFiles(directory="static", html=True), name="static")


# ─────────────────────────────────────────
#   REQUEST / RESPONSE MODELS
# ─────────────────────────────────────────
class ShortenRequest(BaseModel):
    original_url: HttpUrl  # Pydantic validates it's a real URL

class ShortenResponse(BaseModel):
    short_code: str
    short_url: str
    original_url: str

class FeedbackRequest(BaseModel):
    short_code: str = Field(..., min_length=1, max_length=10)
    rating: int = Field(..., ge=1, le=5)
    feedback: str | None = Field(None, max_length=400)


# ─────────────────────────────────────────
#   ENDPOINTS
# ─────────────────────────────────────────

@app.get("/")
async def root():
    """Health check."""
    return {"status": "Treecom URL Shortener is running"}


# ── 1. SHORTEN ──────────────────────────
@app.post("/shorten", response_model=ShortenResponse)
async def shorten_url(request: ShortenRequest):
    """
    Insert the original URL, get the auto-increment ID,
    Base62-encode it as the short code, then update the row.
    """
    original = str(request.original_url)
    conn = get_db()
    cursor = conn.cursor()

    try:
        # Step 1 — insert with a temp placeholder so we get the new ID
        cursor.execute(
            "INSERT INTO urls (original_url, short_code) VALUES (%s, %s)",
            (original, "__tmp__")
        )
        new_id = cursor.lastrowid  # the sequential ID

        # Step 2 — encode the ID to Base62
        short_code = encode_base62(new_id)

        # Step 3 — update the row with the real short code
        cursor.execute(
            "UPDATE urls SET short_code = %s WHERE id = %s",
            (short_code, new_id)
        )
        conn.commit()

        base_url = os.getenv("BASE_URL", "https://treecom.io")
        return ShortenResponse(
            short_code=short_code,
            short_url=f"{base_url}/{short_code}",
            original_url=original,
        )

    except mysql.connector.IntegrityError:
        conn.rollback()
        raise HTTPException(status_code=409, detail="Short code collision — please retry.")
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Server error: {e}")
    finally:
        cursor.close()
        conn.close()


# ── 2. REDIRECT ─────────────────────────
@app.get("/{short_code}")
async def redirect_to_original(short_code: str):
    """
    Look up the short code and redirect the user.
    Also increments the click counter.
    """
    # Safety: short codes are max 10 alphanumeric chars
    if not short_code.isalnum() or len(short_code) > 10:
        raise HTTPException(status_code=400, detail="Invalid short code.")

    conn = get_db()
    cursor = conn.cursor(dictionary=True)

    try:
        cursor.execute(
            "SELECT id, original_url FROM urls WHERE short_code = %s",
            (short_code,)
        )
        row = cursor.fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="Short URL not found.")

        # Fire-and-forget click increment
        cursor.execute(
            "UPDATE urls SET click_count = click_count + 1 WHERE id = %s",
            (row["id"],)
        )
        conn.commit()

        # 302 = temporary redirect (won't be cached by browsers aggressively)
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
    """Save star rating and optional text feedback."""
    conn = get_db()
    cursor = conn.cursor()

    try:
        # Verify the short_code actually exists
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


# ── 4. STATS (bonus) ────────────────────
@app.get("/stats/{short_code}")
async def get_stats(short_code: str):
    """Return click count and basic info for a short code."""
    conn = get_db()
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
