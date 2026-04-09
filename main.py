from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from openai import OpenAI
import os

app = FastAPI()

# Static + templates (if you’re using them)
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# OpenAI client
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Request model
class Prompt(BaseModel):
    message: str

# Health check
@app.get("/health")
async def health():
    return {"status": "ok"}

# TEMP MEMORY (resets on deploy)
chat_history = []

# Home page
@app.get("/", response_class=HTMLResponse)
async def home():
    return """
    <html>
    <body style="background:#111;color:white;font-family:sans-serif;padding:20px;">
        <h2>AI Engine Live 🔥</h2>
        <input id="msg" placeholder="Type message..." style="width:80%;padding:10px;">
        <button onclick="send()">Send</button>
        <button onclick="clearChat()">New Chat</button>
        <pre id="chat"></pre>

        <script>
        async function send() {
            const msg = document.getElementById("msg").value;

            const res = await fetch("/chat", {
                method: "POST",
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify({message: msg})
            });

            const data = await res.json();
            document.getElementById("chat").innerText += "\\nYou: " + msg;
            document.getElementById("chat").innerText += "\\nAI: " + data.reply + "\\n";
        }

        async function clearChat() {
            await fetch("/clear", { method: "POST" });
            document.getElementById("chat").innerText = "";
        }
        </script>
    </body>
    </html>
    """

# Chat endpoint
@app.post("/chat")
async def chat(prompt: Prompt):
    global chat_history

    user_message = prompt.message.strip()

    if not user_message:
        return JSONResponse({
            "reply": "Say something and I’ll reply.",
            "sources": []
        })

    # Store user message
    chat_history.append({
        "role": "user",
        "content": user_message
    })

    try:
        response = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=chat_history
        )

        reply = response.choices[0].message.content

        # Store assistant reply
        chat_history.append({
            "role": "assistant",
            "content": reply
        })

        return JSONResponse({
            "reply": reply,
            "sources": []
        })

    except Exception as e:
        return JSONResponse({
            "reply": f"Error: {str(e)}",
            "sources": []
        })

# Clear chat memory
@app.post("/clear")
async def clear_chat():
    global chat_history
    chat_history = []
    return {"status": "cleared"}

# Run app (for local, safe to leave)
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)
