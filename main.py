from fastapi import FastAPI, Request, Form, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from openai import OpenAI
from sqlalchemy import create_engine, Column, Integer, String, Text, ForeignKey, DateTime
from sqlalchemy.orm import sessionmaker, declarative_base, relationship, Session
from passlib.context import CryptContext
from starlette.middleware.sessions import SessionMiddleware
from datetime import datetime
import os

app = FastAPI()

app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SESSION_SECRET", "super-secret"),
)

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

DATABASE_URL = "sqlite:///./app.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine)

Base = declarative_base()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# ---------------- MODELS ----------------

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True)
    password_hash = Column(String)

    conversations = relationship("Conversation", back_populates="user")


class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True)
    title = Column(String, default="New Chat")
    user_id = Column(Integer, ForeignKey("users.id"))

    user = relationship("User", back_populates="conversations")
    messages = relationship("Message", back_populates="conversation")


class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id"))
    role = Column(String)
    content = Column(Text)

    conversation = relationship("Conversation", back_populates="messages")


Base.metadata.create_all(bind=engine)


# ---------------- HELPERS ----------------

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def hash_password(password):
    return pwd_context.hash(password)


def verify_password(password, hashed):
    return pwd_context.verify(password, hashed)


def get_user(request, db):
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    return db.query(User).filter(User.id == user_id).first()


# ---------------- ROUTES ----------------

@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "error": None})


@app.get("/signup", response_class=HTMLResponse)
def signup_page(request: Request):
    return templates.TemplateResponse("signup.html", {"request": request, "error": None})


@app.post("/signup")
def signup(request: Request, username: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    if db.query(User).filter(User.username == username).first():
        return templates.TemplateResponse("signup.html", {"request": request, "error": "Username taken"})

    user = User(username=username, password_hash=hash_password(password))
    db.add(user)
    db.commit()

    request.session["user_id"] = user.id
    return RedirectResponse("/", status_code=303)


@app.post("/login")
def login(request: Request, username: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == username).first()

    if not user or not verify_password(password, user.password_hash):
        return templates.TemplateResponse("login.html", {"request": request, "error": "Invalid login"})

    request.session["user_id"] = user.id
    return RedirectResponse("/", status_code=303)


@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


@app.get("/", response_class=HTMLResponse)
def home(request: Request, db: Session = Depends(get_db)):
    user = get_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)

    conversations = db.query(Conversation).filter(Conversation.user_id == user.id).all()

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "user": user,
            "conversations": conversations,
            "active_conversation": None,
            "messages": [],
        }
    )


@app.get("/new-chat")
def new_chat(request: Request, db: Session = Depends(get_db)):
    user = get_user(request, db)
    convo = Conversation(user_id=user.id)
    db.add(convo)
    db.commit()

    return RedirectResponse(f"/chat/{convo.id}", status_code=303)


@app.get("/chat/{conversation_id}", response_class=HTMLResponse)
def open_chat(conversation_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_user(request, db)

    convo = db.query(Conversation).filter(Conversation.id == conversation_id).first()
    messages = db.query(Message).filter(Message.conversation_id == convo.id).all()

    conversations = db.query(Conversation).filter(Conversation.user_id == user.id).all()

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "user": user,
            "conversations": conversations,
            "active_conversation": convo,
            "messages": messages,
        }
    )


class ChatPayload(BaseModel):
    message: str
    conversation_id: int | None = None


@app.post("/chat")
def chat(payload: ChatPayload, request: Request, db: Session = Depends(get_db)):
    user = get_user(request, db)

    convo = db.query(Conversation).filter(Conversation.id == payload.conversation_id).first()

    user_msg = Message(conversation_id=convo.id, role="user", content=payload.message)
    db.add(user_msg)
    db.commit()

    history = db.query(Message).filter(Message.conversation_id == convo.id).all()

    messages = [{"role": m.role, "content": m.content} for m in history]

    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=messages,
    )

    reply = response.choices[0].message.content

    ai_msg = Message(conversation_id=convo.id, role="assistant", content=reply)
    db.add(ai_msg)
    db.commit()

    return JSONResponse({"reply": reply, "conversation_id": convo.id})
