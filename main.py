from datetime import datetime
from typing import Optional
import html
import json
import os

from fastapi import FastAPI, Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from pydantic import BaseModel
from openai import OpenAI
from passlib.context import CryptContext
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy import create_engine, Column, Integer, String, Text, ForeignKey, DateTime
from sqlalchemy.orm import sessionmaker, declarative_base, relationship, Session


app = FastAPI()

app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SESSION_SECRET", "change-me-now"),
)

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

DATABASE_URL = "sqlite:///./app.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")


# -----------------------------
# Database models
# -----------------------------
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    conversations = relationship("Conversation", back_populates="user", cascade="all, delete-orphan")


class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), default="New Chat")
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="conversations")
    messages = relationship("Message", back_populates="conversation", cascade="all, delete-orphan")


class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id"), nullable=False)
    role = Column(String(20), nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    conversation = relationship("Conversation", back_populates="messages")


Base.metadata.create_all(bind=engine)


# -----------------------------
# Pydantic model
# -----------------------------
class ChatPayload(BaseModel):
    message: str
    conversation_id: Optional[int] = None


# -----------------------------
# Helpers
# -----------------------------
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def hash_password(password: str) -> str:
    password = password[:72]  # bcrypt limit
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    password = password[:72]  # must match hashing
    return pwd_context.verify(password, password_hash)


def get_current_user(request: Request, db: Session) -> Optional[User]:
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    return db.query(User).filter(User.id == user_id).first()


def get_user_conversations(db: Session, user_id: int):
    return (
        db.query(Conversation)
        .filter(Conversation.user_id == user_id)
        .order_by(Conversation.created_at.desc())
        .all()
    )


def get_conversation_for_user(db: Session, user_id: int, conversation_id: int) -> Optional[Conversation]:
    return (
        db.query(Conversation)
        .filter(Conversation.id == conversation_id, Conversation.user_id == user_id)
        .first()
    )


def create_conversation(db: Session, user_id: int, title: str = "New Chat") -> Conversation:
    convo = Conversation(title=title, user_id=user_id)
    db.add(convo)
    db.commit()
    db.refresh(convo)
    return convo


def page_shell(title: str, body: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{html.escape(title)}</title>
  <style>
    * {{
      box-sizing: border-box;
    }}
    body {{
      margin: 0;
      font-family: Arial, Helvetica, sans-serif;
      background: #0f1115;
      color: #fff;
    }}
    a {{
      color: inherit;
      text-decoration: none;
    }}
    .auth-page {{
      min-height: 100vh;
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 20px;
    }}
    .auth-card {{
      width: 100%;
      max-width: 400px;
      background: #171a21;
      border: 1px solid #262b36;
      border-radius: 18px;
      padding: 24px;
    }}
    .auth-form {{
      display: flex;
      flex-direction: column;
      gap: 12px;
      margin-top: 16px;
    }}
    .auth-form input {{
      padding: 14px 16px;
      border-radius: 12px;
      border: 1px solid #2a3140;
      background: #1b2030;
      color: white;
      font-size: 16px;
    }}
    .auth-form button {{
      padding: 14px 16px;
      border: none;
      border-radius: 12px;
      background: #2b6cff;
      color: white;
      font-weight: bold;
      cursor: pointer;
    }}
    .muted {{
      color: #9ea7b8;
      font-size: 14px;
    }}
    .error-box {{
      background: #481d24;
      border: 1px solid #7d2c39;
      color: #ffc7d0;
      padding: 12px;
      border-radius: 10px;
      margin-top: 12px;
      margin-bottom: 12px;
    }}
    .app-shell {{
      display: flex;
      min-height: 100vh;
    }}
    .sidebar {{
      width: 280px;
      background: #171a21;
      border-right: 1px solid #262b36;
      padding: 16px;
      display: flex;
      flex-direction: column;
      gap: 16px;
    }}
    .btn {{
      display: inline-block;
      background: #2b6cff;
      color: white;
      border: none;
      padding: 10px 14px;
      border-radius: 10px;
      text-align: center;
      cursor: pointer;
    }}
    .conversation-list {{
      display: flex;
      flex-direction: column;
      gap: 8px;
      overflow-y: auto;
    }}
    .conversation-item {{
      background: #202533;
      padding: 12px;
      border-radius: 10px;
      color: #d8deea;
      word-break: break-word;
    }}
    .conversation-item.active {{
      background: #2b6cff;
      color: #fff;
    }}
    .chat-panel {{
      flex: 1;
      display: flex;
      flex-direction: column;
      min-height: 100vh;
    }}
    .chat-header {{
      padding: 18px 20px;
      border-bottom: 1px solid #262b36;
      background: #11151d;
    }}
    .messages {{
      flex: 1;
      overflow-y: auto;
      padding: 20px;
      display: flex;
      flex-direction: column;
      gap: 14px;
    }}
    .message-row {{
      display: flex;
    }}
    .message-row.user {{
      justify-content: flex-end;
    }}
    .message-row.assistant {{
      justify-content: flex-start;
    }}
    .message-bubble {{
      max-width: 80%;
      padding: 14px 16px;
      border-radius: 16px;
      line-height: 1.5;
      white-space: pre-wrap;
      word-break: break-word;
    }}
    .message-row.user .message-bubble {{
      background: #2b6cff;
      color: white;
      border-bottom-right-radius: 6px;
    }}
    .message-row.assistant .message-bubble {{
      background: #202533;
      color: #eef2f9;
      border-bottom-left-radius: 6px;
    }}
    .chat-form {{
      display: flex;
      gap: 12px;
      padding: 16px;
      border-top: 1px solid #262b36;
      background: #11151d;
    }}
    .chat-form input {{
      flex: 1;
      padding: 14px 16px;
      border-radius: 12px;
      border: 1px solid #2a3140;
      background: #1b2030;
      color: white;
      font-size: 16px;
    }}
    .chat-form button {{
      padding: 14px 18px;
      border: none;
      border-radius: 12px;
      background: #2b6cff;
      color: white;
      font-weight: bold;
      cursor: pointer;
    }}
    .top-row {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 12px;
    }}
    @media (max-width: 768px) {{
      .app-shell {{
        flex-direction: column;
      }}
      .sidebar {{
        width: 100%;
        border-right: none;
        border-bottom: 1px solid #262b36;
      }}
      .message-bubble {{
        max-width: 92%;
      }}
    }}
  </style>
</head>
<body>
{body}
</body>
</html>"""


def render_login_page(error: Optional[str] = None) -> str:
    error_html = f'<div class="error-box">{html.escape(error)}</div>' if error else ""
    body = f"""
    <div class="auth-page">
      <div class="auth-card">
        <h1>Login</h1>
        <p class="muted">Welcome back.</p>
        {error_html}
        <form method="post" action="/login" class="auth-form">
          <input type="text" name="username" placeholder="Username" required />
          <input type="password" name="password" placeholder="Password" required />
          <button type="submit">Login</button>
        </form>
        <p class="muted">No account? <a href="/signup">Sign up</a></p>
      </div>
    </div>
    """
    return page_shell("Login", body)


def render_signup_page(error: Optional[str] = None) -> str:
    error_html = f'<div class="error-box">{html.escape(error)}</div>' if error else ""
    body = f"""
    <div class="auth-page">
      <div class="auth-card">
        <h1>Sign Up</h1>
        <p class="muted">Create your account.</p>
        {error_html}
        <form method="post" action="/signup" class="auth-form">
          <input type="text" name="username" placeholder="Username" required />
          <input type="password" name="password" placeholder="Password" required />
          <button type="submit">Create Account</button>
        </form>
        <p class="muted">Already have an account? <a href="/login">Login</a></p>
      </div>
    </div>
    """
    return page_shell("Sign Up", body)


def render_chat_page(user: User, conversations, active_conversation, messages) -> str:
    convo_links = []
    for convo in conversations:
        active_class = " active" if active_conversation and convo.id == active_conversation.id else ""
        convo_links.append(
            f'<a class="conversation-item{active_class}" href="/chat/{convo.id}">{html.escape(convo.title)}</a>'
        )
    convo_html = "\n".join(convo_links) if convo_links else '<p class="muted">No chats yet.</p>'

    msg_html_parts = []
    for msg in messages:
        role = "assistant"
        if msg.role == "user":
            role = "user"
        msg_html_parts.append(
            f'<div class="message-row {role}"><div class="message-bubble">{html.escape(msg.content)}</div></div>'
        )
    msg_html = "\n".join(msg_html_parts) if msg_html_parts else '<p class="muted">Start a new chat below.</p>'

    active_title = html.escape(active_conversation.title) if active_conversation else "New Chat"
    conversation_id_js = "null" if active_conversation is None else json.dumps(active_conversation.id)

    body = f"""
    <div class="app-shell">
      <aside class="sidebar">
        <div class="top-row">
          <div>
            <h2>Chats</h2>
            <p class="muted">Logged in as <strong>{html.escape(user.username)}</strong></p>
          </div>
          <a class="btn" href="/logout">Logout</a>
        </div>

        <a class="btn" href="/new-chat">+ New Chat</a>

        <div class="conversation-list">
          {convo_html}
        </div>
      </aside>

      <main class="chat-panel">
        <div class="chat-header">
          <h1>{active_title}</h1>
        </div>

        <div id="messages" class="messages">
          {msg_html}
        </div>

        <form id="chat-form" class="chat-form">
          <input id="message-input" type="text" name="message" placeholder="Message your AI..." autocomplete="off" required />
          <button type="submit">Send</button>
        </form>
      </main>
    </div>

    <script>
      let conversationId = {conversation_id_js};
      const form = document.getElementById("chat-form");
      const input = document.getElementById("message-input");
      const messages = document.getElementById("messages");

      function addMessage(role, text) {{
        const row = document.createElement("div");
        row.className = "message-row " + role;

        const bubble = document.createElement("div");
        bubble.className = "message-bubble";
        bubble.textContent = text;

        row.appendChild(bubble);
        messages.appendChild(row);
        messages.scrollTop = messages.scrollHeight;
      }}

      form.addEventListener("submit", async (e) => {{
        e.preventDefault();

        const text = input.value.trim();
        if (!text) return;

        addMessage("user", text);
        input.value = "";
        input.disabled = true;

        try {{
          const res = await fetch("/chat", {{
            method: "POST",
            headers: {{
              "Content-Type": "application/json"
            }},
            body: JSON.stringify({{
              message: text,
              conversation_id: conversationId
            }})
          }});

          const data = await res.json();
          addMessage("assistant", data.reply);

          if (!conversationId && data.conversation_id) {{
            window.location.href = "/chat/" + data.conversation_id;
          }}
        }} catch (err) {{
          addMessage("assistant", "Something went wrong.");
        }} finally {{
          input.disabled = false;
          input.focus();
        }}
      }});
    </script>
    """
    return page_shell("AI Engine", body)


# -----------------------------
# Auth routes
# -----------------------------
@app.get("/login", response_class=HTMLResponse)
def login_page():
    return HTMLResponse(render_login_page())


@app.get("/signup", response_class=HTMLResponse)
def signup_page():
    return HTMLResponse(render_signup_page())


@app.post("/signup")
def signup(username: str = Form(...), password: str = Form(...), request: Request = None, db: Session = Depends(get_db)):
    username = username.strip()

    if len(username) < 3:
        return HTMLResponse(render_signup_page("Username must be at least 3 characters."))

    if len(password) < 6:
        return HTMLResponse(render_signup_page("Password must be at least 6 characters."))

    existing_user = db.query(User).filter(User.username == username).first()
    if existing_user:
        return HTMLResponse(render_signup_page("Username already taken."))

    user = User(username=username, password_hash=hash_password(password))
    db.add(user)
    db.commit()
    db.refresh(user)

    request.session["user_id"] = user.id
    return RedirectResponse(url="/", status_code=303)


@app.post("/login")
def login(username: str = Form(...), password: str = Form(...), request: Request = None, db: Session = Depends(get_db)):
    username = username.strip()
    user = db.query(User).filter(User.username == username).first()

    if not user or not verify_password(password, user.password_hash):
        return HTMLResponse(render_login_page("Invalid username or password."))

    request.session["user_id"] = user.id
    return RedirectResponse(url="/", status_code=303)


@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)


# -----------------------------
# App routes
# -----------------------------
@app.get("/", response_class=HTMLResponse)
def home(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=303)

    conversations = get_user_conversations(db, user.id)
    active_conversation = conversations[0] if conversations else None

    if active_conversation:
        messages = (
            db.query(Message)
            .filter(Message.conversation_id == active_conversation.id)
            .order_by(Message.created_at.asc())
            .all()
        )
    else:
        messages = []

    return HTMLResponse(render_chat_page(user, conversations, active_conversation, messages))


@app.get("/new-chat")
def new_chat(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=303)

    convo = create_conversation(db, user.id)
    return RedirectResponse(url=f"/chat/{convo.id}", status_code=303)


@app.get("/chat/{conversation_id}", response_class=HTMLResponse)
def open_chat(conversation_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=303)

    active_conversation = get_conversation_for_user(db, user.id, conversation_id)
    if not active_conversation:
        return RedirectResponse(url="/", status_code=303)

    conversations = get_user_conversations(db, user.id)
    messages = (
        db.query(Message)
        .filter(Message.conversation_id == active_conversation.id)
        .order_by(Message.created_at.asc())
        .all()
    )

    return HTMLResponse(render_chat_page(user, conversations, active_conversation, messages))


# -----------------------------
# Chat API
# -----------------------------
@app.post("/chat")
def chat(payload: ChatPayload, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"reply": "Please log in first.", "conversation_id": None}, status_code=401)

    user_message = payload.message.strip()
    if not user_message:
        return JSONResponse({"reply": "Say something and I’ll reply.", "conversation_id": payload.conversation_id})

    conversation = None
    if payload.conversation_id is not None:
        conversation = get_conversation_for_user(db, user.id, payload.conversation_id)

    if conversation is None:
        title = user_message[:40] if user_message else "New Chat"
        conversation = create_conversation(db, user.id, title=title)

    user_db_message = Message(conversation_id=conversation.id, role="user", content=user_message)
    db.add(user_db_message)
    db.commit()

    history = (
        db.query(Message)
        .filter(Message.conversation_id == conversation.id)
        .order_by(Message.created_at.asc())
        .all()
    )

    openai_messages = [{"role": msg.role, "content": msg.content} for msg in history]

    try:
        response = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=openai_messages,
        )
        assistant_reply = response.choices[0].message.content or "No reply returned."
    except Exception as e:
        assistant_reply = f"Error talking to AI: {str(e)}"

    ai_db_message = Message(conversation_id=conversation.id, role="assistant", content=assistant_reply)
    db.add(ai_db_message)
    db.commit()

    return JSONResponse({"reply": assistant_reply, "conversation_id": conversation.id})
