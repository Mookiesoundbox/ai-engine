from datetime import datetime
from typing import Optional

import os
from fastapi import FastAPI, Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
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

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

DATABASE_URL = "sqlite:///./app.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


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
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)


def get_current_user(request: Request, db: Session) -> Optional[User]:
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    return db.query(User).filter(User.id == user_id).first()


def require_user(request: Request, db: Session) -> User:
    user = get_current_user(request, db)
    if not user:
        raise Exception("User not logged in")
    return user


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


# -----------------------------
# Auth routes
# -----------------------------
@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@app.get("/signup", response_class=HTMLResponse)
def signup_page(request: Request):
    return templates.TemplateResponse("signup.html", {"request": request})


@app.post("/signup")
def signup(request: Request, username: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    username = username.strip()

    if len(username) < 3:
        return templates.TemplateResponse("signup.html", {"request": request, "error": "Username must be at least 3 characters."})

    if len(password) < 6:
        return templates.TemplateResponse("signup.html", {"request": request, "error": "Password must be at least 6 characters."})

    existing_user = db.query(User).filter(User.username == username).first()
    if existing_user:
        return templates.TemplateResponse("signup.html", {"request": request, "error": "Username already taken."})

    user = User(username=username, password_hash=hash_password(password))
    db.add(user)
    db.commit()
    db.refresh(user)

    request.session["user_id"] = user.id
    return RedirectResponse(url="/", status_code=303)


@app.post("/login")
def login(request: Request, username: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    username = username.strip()
    user = db.query(User).filter(User.username == username).first()

    if not user or not verify_password(password, user.password_hash):
        return templates.TemplateResponse("login.html", {"request": request, "error": "Invalid username or password."})

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

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "user": user,
            "conversations": conversations,
            "active_conversation": active_conversation,
            "messages": messages,
        },
    )


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

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "user": user,
            "conversations": conversations,
            "active_conversation": active_conversation,
            "messages": messages,
        },
    )


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
