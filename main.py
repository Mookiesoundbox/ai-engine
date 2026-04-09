from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from openai import OpenAI
import os
import sqlite3
import uuid
from datetime import datetime

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

DB_FILE = "memory.db"


class Prompt(BaseModel):
    message: str


def init_db():
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    conn.commit()
    conn.close()


def save_message(session_id: str, role: str, content: str):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO messages (session_id, role, content, created_at)
        VALUES (?, ?, ?, ?)
    """, (session_id, role, content, datetime.utcnow().isoformat()))

    conn.commit()
    conn.close()


def get_recent_messages(session_id: str, limit: int = 12):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()

    cur.execute("""
        SELECT role, content
        FROM messages
        WHERE session_id = ?
        ORDER BY id DESC
        LIMIT ?
    """, (session_id, limit))

    rows = cur.fetchall()
    conn.close()

    rows.reverse()

    return [{"role": role, "content": content} for role, content in rows]


init_db()


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    session_id = request.cookies.get("session_id")

    if not session_id:
        session_id = str(uuid.uuid4())

    response = templates.TemplateResponse("index.html", {"request": request})
    response.set_cookie(
        key="session_id",
        value=session_id,
        httponly=True,
        samesite="lax"
    )
    return response


@app.post("/chat")
async def chat(prompt: Prompt, request: Request):
    user_message = prompt.message.strip()

    if not user_message:
        return JSONResponse({
            "reply": "Say something and I’ll reply.",
            "sources": []
        })

    session_id = request.cookies.get("session_id")
    if not session_id:
        session_id = str(uuid.uuid4())

    try:
        system_prompt = {
            "role": "system",
            "content": (
                "You are a highly intelligent, practical AI assistant. "
                "You speak in a confident, friendly tone. "
                "You explain things clearly and naturally. "
                "You adapt to the user's style. "
                "Remember useful details from earlier messages in this conversation history."
            )
        }

        save_message(session_id, "user", user_message)

        recent_history = get_recent_messages(session_id, limit=12)
        messages = [system_prompt] + recent_history

        response = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=messages,
        )

        reply = response.choices[0].message.content or "No reply returned."

        save_message(session_id, "assistant", reply)

        json_response = JSONResponse({
            "reply": reply,
            "sources": []
        })

        json_response.set_cookie(
            key="session_id",
            value=session_id,
            httponly=True,
            samesite="lax"
        )

        return json_response

    except Exception as e:
        return JSONResponse({
            "reply": f"Error: {str(e)}",
            "sources": []
        })
