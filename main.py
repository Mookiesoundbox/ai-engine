from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from openai import OpenAI
from starlette.middleware.sessions import SessionMiddleware
import os
import uuid

app = FastAPI()

# Secret key for browser sessions
app.add_middleware(
    SessionMiddleware,
    secret_key=os.environ.get("SESSION_SECRET", "change-this-secret-key"),
    same_site="lax",
    https_only=False
)

api_key = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=api_key) if api_key else None

class Prompt(BaseModel):
    message: str

# In-memory store for session chats
# Note: resets on deploy/restart
chat_store = {}

def get_session_id(request: Request) -> str:
    session_id = request.session.get("session_id")
    if not session_id:
        session_id = str(uuid.uuid4())
        request.session["session_id"] = session_id
    return session_id

def get_chat_history(request: Request) -> list:
    session_id = get_session_id(request)
    if session_id not in chat_store:
        chat_store[session_id] = []
    return chat_store[session_id]

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "has_api_key": bool(api_key),
        "sessions_in_memory": len(chat_store)
    }

@app.get("/", response_class=HTMLResponse)
async def home():
    return """
    <html>
    <head>
        <title>AI Engine</title>
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <style>
            body {
                margin: 0;
                padding: 0;
                background: #111;
                color: white;
                font-family: -apple-system, BlinkMacSystemFont, sans-serif;
            }
            .wrap {
                max-width: 700px;
                margin: 0 auto;
                padding: 16px;
            }
            h2 {
                margin-top: 0;
            }
            #chat {
                background: #1a1a1a;
                border-radius: 14px;
                padding: 12px;
                min-height: 300px;
                white-space: pre-wrap;
                overflow-wrap: break-word;
                margin-bottom: 12px;
            }
            .row {
                display: flex;
                gap: 8px;
            }
            input {
                flex: 1;
                padding: 14px;
                border-radius: 12px;
                border: none;
                font-size: 16px;
            }
            button {
                padding: 14px 16px;
                border-radius: 12px;
                border: none;
                font-size: 16px;
                cursor: pointer;
            }
            .topbar {
                display: flex;
                gap: 8px;
                margin-bottom: 12px;
            }
        </style>
    </head>
    <body>
        <div class="wrap">
            <h2>AI Engine Live</h2>

            <div class="topbar">
                <button onclick="clearChat()">New Chat</button>
            </div>

            <div id="chat"></div>

            <div class="row">
                <input id="msg" placeholder="Type message..." />
                <button onclick="send()">Send</button>
            </div>
        </div>

        <script>
            const chatBox = document.getElementById("chat");
            const msgInput = document.getElementById("msg");

            function addLine(text) {
                chatBox.innerText += text + "\\n\\n";
                chatBox.scrollTop = chatBox.scrollHeight;
            }

            async function send() {
                const msg = msgInput.value.trim();
                if (!msg) return;

                addLine("You: " + msg);
                msgInput.value = "";

                try {
                    const res = await fetch("/chat", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ message: msg })
                    });

                    const data = await res.json();
                    addLine("AI: " + data.reply);
                } catch (err) {
                    addLine("AI: Error talking to server.");
                }
            }

            async function clearChat() {
                await fetch("/clear", { method: "POST" });
                chatBox.innerText = "";
            }

            msgInput.addEventListener("keydown", function(event) {
                if (event.key === "Enter") {
                    send();
                }
            });
        </script>
    </body>
    </html>
    """

@app.post("/chat")
async def chat(prompt: Prompt, request: Request):
    if client is None:
        return JSONResponse(
            {
                "reply": "OPENAI_API_KEY is missing in environment variables.",
                "sources": []
            },
            status_code=500
        )

    user_message = prompt.message.strip()

    if not user_message:
        return JSONResponse({
            "reply": "Say something and I’ll reply.",
            "sources": []
        })

    chat_history = get_chat_history(request)

    chat_history.append({
        "role": "user",
        "content": user_message
    })

    try:
        response = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=chat_history
        )

        reply = response.choices[0].message.content or "No reply returned."

        chat_history.append({
            "role": "assistant",
            "content": reply
        })

        return JSONResponse({
            "reply": reply,
            "sources": []
        })

    except Exception as e:
        return JSONResponse(
            {
                "reply": f"OpenAI error: {str(e)}",
                "sources": []
            },
            status_code=500
        )

@app.post("/clear")
async def clear_chat(request: Request):
    session_id = get_session_id(request)
    chat_store[session_id] = []
    return {"status": "cleared"}

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)
