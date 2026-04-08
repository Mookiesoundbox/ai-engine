from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from openai import OpenAI
import os

app = FastAPI()

api_key = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=api_key) if api_key else None


class Prompt(BaseModel):
    message: str


HTML_PAGE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover" />
    <title>AI Engine</title>
    <style>
        * {
            box-sizing: border-box;
        }

        html, body {
            margin: 0;
            padding: 0;
            background: #0b0b0f;
            color: #ffffff;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            min-height: 100%;
        }

        body {
            display: flex;
            justify-content: center;
            padding: 20px 14px;
        }

        .app {
            width: 100%;
            max-width: 760px;
            display: flex;
            flex-direction: column;
            gap: 14px;
        }

        .card {
            background: #15151d;
            border: 1px solid #2a2a36;
            border-radius: 18px;
            padding: 16px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.25);
        }

        .title {
            font-size: 28px;
            font-weight: 800;
            margin: 0 0 6px;
        }

        .sub {
            margin: 0;
            color: #b6b6c7;
            font-size: 14px;
            line-height: 1.5;
        }

        .chat-box {
            min-height: 320px;
            max-height: 58vh;
            overflow-y: auto;
            display: flex;
            flex-direction: column;
            gap: 12px;
            padding-bottom: 4px;
        }

        .msg {
            padding: 12px 14px;
            border-radius: 14px;
            white-space: pre-wrap;
            line-height: 1.5;
            word-wrap: break-word;
        }

        .user {
            background: #2563eb;
            align-self: flex-end;
        }

        .assistant {
            background: #22222d;
            align-self: flex-start;
        }

        .composer {
            display: flex;
            gap: 10px;
            align-items: flex-end;
        }

        textarea {
            flex: 1;
            min-height: 56px;
            max-height: 180px;
            resize: vertical;
            border: 1px solid #343444;
            border-radius: 14px;
            background: #101018;
            color: white;
            padding: 14px;
            font-size: 16px;
            outline: none;
        }

        button {
            border: none;
            border-radius: 14px;
            background: #22c55e;
            color: #08110c;
            font-weight: 800;
            padding: 14px 18px;
            font-size: 16px;
            cursor: pointer;
        }

        button:disabled {
            opacity: 0.6;
            cursor: not-allowed;
        }

        .status {
            color: #a1a1b5;
            font-size: 13px;
            margin-top: 4px;
            min-height: 18px;
        }
    </style>
</head>
<body>
    <div class="app">
        <div class="card">
            <h1 class="title">AI Engine</h1>
            <p class="sub">Your mobile-first private AI launcher is online.</p>
        </div>

        <div class="card">
            <div id="chat" class="chat-box">
                <div class="msg assistant">Engine online. Ask me something.</div>
            </div>
        </div>

        <div class="card">
            <div class="composer">
                <textarea id="message" placeholder="Type your message..."></textarea>
                <button id="sendBtn">Send</button>
            </div>
            <div id="status" class="status"></div>
        </div>
    </div>

    <script>
        const chat = document.getElementById("chat");
        const messageInput = document.getElementById("message");
        const sendBtn = document.getElementById("sendBtn");
        const statusEl = document.getElementById("status");

        function addMessage(text, type) {
            const div = document.createElement("div");
            div.className = `msg ${type}`;
            div.textContent = text;
            chat.appendChild(div);
            chat.scrollTop = chat.scrollHeight;
        }

        async function sendMessage() {
            const text = messageInput.value.trim();
            if (!text) return;

            addMessage(text, "user");
            messageInput.value = "";
            sendBtn.disabled = true;
            statusEl.textContent = "Thinking...";

            try {
                const res = await fetch("/chat", {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json"
                    },
                    body: JSON.stringify({ message: text })
                });

                const data = await res.json();

                if (!res.ok) {
                    addMessage(data.reply || "Something went wrong.", "assistant");
                } else {
                    addMessage(data.reply || "No response.", "assistant");
                }
            } catch (err) {
                addMessage("Network error. Please try again.", "assistant");
            } finally {
                sendBtn.disabled = false;
                statusEl.textContent = "";
            }
        }

        sendBtn.addEventListener("click", sendMessage);

        messageInput.addEventListener("keydown", function(event) {
            if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                sendMessage();
            }
        });
    </script>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
async def home():
    return HTMLResponse(content=HTML_PAGE)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/chat")
async def chat(prompt: Prompt):
    user_message = prompt.message.strip()

    if not user_message:
        return JSONResponse(
            {
                "reply": "Say something and I’ll reply.",
                "sources": []
            }
        )

    if client is None:
        return JSONResponse(
            {
                "reply": "OPENAI_API_KEY is missing in Render environment variables.",
                "sources": []
            },
            status_code=500
        )

    try:
        response = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
                {"role": "user", "content": user_message}
            ]
        )

        reply_text = response.choices[0].message.content or "No response from AI."

        return JSONResponse(
            {
                "reply": reply_text,
                "sources": []
            }
        )

    except Exception as e:
        return JSONResponse(
            {
                "reply": f"Error: {str(e)}",
                "sources": []
            },
            status_code=500
        )


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)
