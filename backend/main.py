from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
import mysql.connector
import os
from fastapi.responses import JSONResponse

app = FastAPI()


# -----------------------------
#   DATA MODEL
# -----------------------------
class UserRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)


# -----------------------------
#   DB CONNECTION
# -----------------------------
def get_db_connection():
    try:
        return mysql.connector.connect(
            host=os.getenv("DB_HOST"),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD"),
            database=os.getenv("DB_NAME"),
            port=int(os.getenv("DB_PORT")),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database connection error: {str(e)}")


# -----------------------------
#   HEALTH CHECK
# -----------------------------
@app.get("/")
async def root():
    return {"message": "Backend is running"}


# -----------------------------
#   INSERT ENDPOINT
# -----------------------------
@app.post("/submit")
async def submit_data(request: UserRequest):

    name = request.name.strip()

    if not name:
        raise HTTPException(status_code=400, detail="Name cannot be empty")

    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Insert the name
        insert_query = "INSERT INTO users (name) VALUES (%s)"
        cursor.execute(insert_query, (name,))
        conn.commit()

        return {
            "status": "success",
            "message": "Name inserted successfully",
            "name": name
        }

    except mysql.connector.Error as db_err:
        if conn:
            conn.rollback()
        raise HTTPException(status_code=500, detail=f"MySQL Error: {str(db_err)}")

    except Exception as e:
        if conn:
            conn.rollback()
        raise HTTPException(status_code=500, detail=f"Server Error: {str(e)}")

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
