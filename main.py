from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from openai import OpenAI
import os
import sqlite3
import uuid
import hashlib
from datetime import datetime

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

DB_FILE = "memory.db"


class Prompt(BaseModel):
    message: str


class LoginRequest(BaseModel):
    username: str
    password: str


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def init_db():
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS memory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            fact_key TEXT NOT NULL,
            fact_value TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(user_id, fact_key)
        )
    """)

    conn.commit()
    conn.close()


def create_user(username: str, password: str) -> bool:
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()

    try:
        cur.execute("""
            INSERT INTO users (username, password_hash, created_at)
            VALUES (?, ?, ?)
        """, (username.strip().lower(), hash_password(password), datetime.utcnow().isoformat()))
        conn.commit()
        success = True
    except sqlite3.IntegrityError:
        success = False

    conn.close()
    return success


def get_user_by_username(username: str):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()

    cur.execute("""
        SELECT id, username, password_hash
        FROM users
        WHERE username = ?
    """, (username.strip().lower(),))

    row = cur.fetchone()
    conn.close()
    return row


def verify_user(username: str, password: str):
    user = get_user_by_username(username)
    if not user:
        return None

    user_id, db_username, password_hash = user
    if hash_password(password) == password_hash:
        return {"id": user_id, "username": db_username}

    return None


def get_user_by_id(user_id: int):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()

    cur.execute("""
        SELECT id, username
        FROM users
        WHERE id = ?
    """, (user_id,))

    row = cur.fetchone()
    conn.close()

    if row:
        return {"id": row[0], "username": row[1]}
    return None


def save_message(user_id: int, role: str, content: str):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO messages (user_id, role, content, created_at)
        VALUES (?, ?, ?, ?)
    """, (user_id, role, content, datetime.utcnow().isoformat()))

    conn.commit()
    conn.close()


def get_recent_messages(user_id: int, limit: int = 12):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()

    cur.execute("""
        SELECT role, content
        FROM messages
        WHERE user_id = ?
        ORDER BY id DESC
        LIMIT ?
    """, (user_id, limit))

    rows = cur.fetchall()
    conn.close()

    rows.reverse()
    return [{"role": role, "content": content} for role, content in rows]


def upsert_memory(user_id: int, fact_key: str, fact_value: str):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO memory (user_id, fact_key, fact_value, updated_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(user_id, fact_key)
        DO UPDATE SET
            fact_value = excluded.fact_value,
            updated_at = excluded.updated_at
    """, (user_id, fact_key, fact_value, datetime.utcnow().isoformat()))

    conn.commit()
    conn.close()


def get_memory(user_id: int):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()

    cur.execute("""
        SELECT fact_key, fact_value
        FROM memory
        WHERE user_id = ?
        ORDER BY updated_at DESC
    """, (user_id,))

    rows = cur.fetchall()
    conn.close()

    return {key: value for key, value in rows}


def delete_memory(user_id: int, fact_key: str):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()

    cur.execute("""
        DELETE FROM memory
        WHERE user_id = ? AND fact_key = ?
    """, (user_id, fact_key))

    conn.commit()
    conn.close()


def extract_and_store_facts(user_id: int, user_message: str):
    text = user_message.strip()
    lower = text.lower()

    if "my name is " in lower:
        idx = lower.find("my name is ")
        name = text[idx + len("my name is "):].strip(" .,!?\n\t")
        if name:
            upsert_memory(user_id, "name", name)

    elif "i am " in lower:
        idx = lower.find("i am ")
        possible_name = text[idx + len("i am "):].strip(" .,!?\n\t")
        if possible_name and len(possible_name.split()) <= 3:
            upsert_memory(user_id, "name", possible_name)

    if "i like " in lower:
        idx = lower.find("i like ")
        preference = text[idx + len("i like "):].strip(" .,!?\n\t")
        if preference:
            upsert_memory(user_id, "likes", preference)

    if "i prefer " in lower:
        idx = lower.find("i prefer ")
        preference = text[idx + len("i prefer "):].strip(" .,!?\n\t")
        if preference:
            upsert_memory(user_id, "preference", preference)

    if "i am building " in lower:
        idx = lower.find("i am building ")
        project = text[idx + len("i am building "):].strip(" .,!?\n\t")
        if project:
            upsert_memory(user_id, "project", project)

    if "my goal is " in lower:
        idx = lower.find("my goal is ")
        goal = text[idx + len("my goal is "):].strip(" .,!?\n\t")
        if goal:
            upsert_memory(user_id, "goal", goal)


def get_logged_in_user(request: Request):
    user_id = request.cookies.get("user_id")
    if not user_id:
        return None

    try:
        user_id = int(user_id)
    except ValueError:
        return None

    return get_user_by_id(user_id)


init_db()


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    user = get_logged_in_user(request)

    if not user:
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={"request": request}
        )

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"request": request, "username": user["username"]}
    )


@app.post("/register")
async def register(login_data: LoginRequest):
    username = login_data.username.strip().lower()
    password = login_data.password.strip()

    if not username or not password:
        return JSONResponse({
            "success": False,
            "reply": "Username and password are required."
        }, status_code=400)

    if len(password) < 6:
        return JSONResponse({
            "success": False,
            "reply": "Password must be at least 6 characters."
        }, status_code=400)

    created = create_user(username, password)

    if not created:
        return JSONResponse({
            "success": False,
            "reply": "Username already exists."
        }, status_code=400)

    user = verify_user(username, password)

    response = JSONResponse({
        "success": True,
        "reply": "Account created.",
        "username": username
    })

    response.set_cookie(
        key="user_id",
        value=str(user["id"]),
        httponly=True,
        samesite="lax"
    )

    return response


@app.post("/login")
async def login(login_data: LoginRequest):
    username = login_data.username.strip().lower()
    password = login_data.password.strip()

    user = verify_user(username, password)

    if not user:
        return JSONResponse({
            "success": False,
            "reply": "Wrong username or password."
        }, status_code=401)

    response = JSONResponse({
        "success": True,
        "reply": "Access granted.",
        "username": user["username"]
    })

    response.set_cookie(
        key="user_id",
        value=str(user["id"]),
        httponly=True,
        samesite="lax"
    )

    return response


@app.post("/logout")
async def logout():
    response = JSONResponse({
        "success": True,
        "reply": "Logged out."
    })

    response.delete_cookie("user_id")
    return response


@app.get("/me")
async def me(request: Request):
    user = get_logged_in_user(request)

    if not user:
        return JSONResponse({"logged_in": False})

    return JSONResponse({
        "logged_in": True,
        "username": user["username"]
    })


@app.post("/chat")
async def chat(prompt: Prompt, request: Request):
    user = get_logged_in_user(request)

    if not user:
        return JSONResponse({
            "reply": "Unauthorized",
            "sources": []
        }, status_code=401)

    user_id = user["id"]
    user_message = prompt.message.strip()
    lower = user_message.lower()

    if not user_message:
        return JSONResponse({
            "reply": "Say something and I’ll reply.",
            "sources": []
        })

    if "what do you remember" in lower:
        memory_facts = get_memory(user_id)
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
        delete_memory(user_id, "name")
        return JSONResponse({
            "reply": "Got it — I’ve forgotten your name.",
            "sources": []
        })

    try:
        save_message(user_id, "user", user_message)
        extract_and_store_facts(user_id, user_message)

        recent_history = get_recent_messages(user_id, limit=12)
        memory_facts = get_memory(user_id)

        if memory_facts:
            memory_text = "\n".join([f"- {key}: {value}" for key, value in memory_facts.items()])
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

        save_message(user_id, "assistant", reply)

        return JSONResponse({
            "reply": reply,
            "sources": [],
            "memory": memory_facts,
            "username": user["username"]
        })

    except Exception as e:
        return JSONResponse({
            "reply": f"Error: {str(e)}",
            "sources": []
        }, status_code=500)
