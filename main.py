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

    cur.execute("""
        CREATE TABLE IF NOT EXISTS memory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            fact_key TEXT NOT NULL,
            fact_value TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(session_id, fact_key)
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


def upsert_memory(session_id: str, fact_key: str, fact_value: str):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO memory (session_id, fact_key, fact_value, updated_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(session_id, fact_key)
        DO UPDATE SET
            fact_value = excluded.fact_value,
            updated_at = excluded.updated_at
    """, (session_id, fact_key, fact_value, datetime.utcnow().isoformat()))

    conn.commit()
    conn.close()


def get_memory(session_id: str):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()

    cur.execute("""
        SELECT fact_key, fact_value
        FROM memory
        WHERE session_id = ?
        ORDER BY updated_at DESC
    """, (session_id,))

    rows = cur.fetchall()
    conn.close()

    return {key: value for key, value in rows}

def delete_memory(session_id: str, fact_key: str):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()

    cur.execute("""
        DELETE FROM memory
        WHERE session_id = ? AND fact_key = ?
    """, (session_id, fact_key))

    conn.commit()
    conn.close()
    
def extract_and_store_facts(session_id: str, user_message: str):
    text = user_message.strip()
    lower = text.lower()

    if "my name is " in lower:
        idx = lower.find("my name is ")
        name = text[idx + len("my name is "):].strip(" .,!?\n\t")
        if name:
            upsert_memory(session_id, "name", name)

    elif "i am " in lower:
        idx = lower.find("i am ")
        possible_name = text[idx + len("i am "):].strip(" .,!?\n\t")
        if possible_name and len(possible_name.split()) <= 3:
            upsert_memory(session_id, "name", possible_name)

    if "i like " in lower:
        idx = lower.find("i like ")
        preference = text[idx + len("i like "):].strip(" .,!?\n\t")
        if preference:
            upsert_memory(session_id, "likes", preference)

    if "i prefer " in lower:
        idx = lower.find("i prefer ")
        preference = text[idx + len("i prefer "):].strip(" .,!?\n\t")
        if preference:
            upsert_memory(session_id, "preference", preference)

    if "i am building " in lower:
        idx = lower.find("i am building ")
        project = text[idx + len("i am building "):].strip(" .,!?\n\t")
        if project:
            upsert_memory(session_id, "project", project)

    if "my goal is " in lower:
        idx = lower.find("my goal is ")
        goal = text[idx + len("my goal is "):].strip(" .,!?\n\t")
        if goal:
            upsert_memory(session_id, "goal", goal)


init_db()


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    session_id = request.cookies.get("session_id")

    if not session_id:
        session_id = str(uuid.uuid4())

    response = templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"request": request}
    )

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
    # 🧠 Memory commands
    lower = user_message.lower()

    if "what do you remember" in lower:
        memory_facts = get_memory(session_id)
        if memory_facts:
            return JSONResponse({
                "reply": "\n".join([f"{k}: {v}" for k, v in memory_facts.items()]),
                "sources": []
            })
        else:
            return JSONResponse({
                "reply": "I don’t have any saved info about you yet.",
                "sources": []
            })

    if "forget my name" in lower:
        delete_memory(session_id, "name")
        return JSONResponse({
            "reply": "Got it — I’ve forgotten your name.",
            "sources": []
        })
    if not user_message:
        return JSONResponse({
            "reply": "Say something and I’ll reply.",
            "sources": []
        })

    session_id = request.cookies.get("session_id")
    if not session_id:
        session_id = str(uuid.uuid4())

    try:
        save_message(session_id, "user", user_message)
        extract_and_store_facts(session_id, user_message)

        recent_history = get_recent_messages(session_id, limit=12)
        memory_facts = get_memory(session_id)

        memory_text = ""
        if memory_facts:
            memory_text = "\n".join(
                [f"- {key}: {value}" for key, value in memory_facts.items()]
            )
        else:
            memory_text = "No saved user facts yet."

        system_prompt = {
            "role": "system",
            "content": (
                "You are a highly intelligent, practical AI assistant. "
                "You speak in a confident, friendly tone. "
                "You explain things clearly and naturally. "
                "You adapt to the user's style. "
                "Use the saved memory facts below when helpful and relevant.\n\n"
                f"Saved user facts:\n{memory_text}"
            )
        }

        messages = [system_prompt] + recent_history

        response = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=messages
        )

        reply = response.choices[0].message.content or "No reply returned."

        save_message(session_id, "assistant", reply)

        json_response = JSONResponse({
            "reply": reply,
            "sources": [],
            "memory": memory_facts
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
        }, status_code=500)
