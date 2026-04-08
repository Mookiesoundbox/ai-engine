from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import os
from openai import OpenAI

app = FastAPI()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

class Prompt(BaseModel):
    message: str

@app.get("/", response_class=HTMLResponse)
def home():
    return """
    <html>
        <head>
            <title>My AI Engine</title>
        </head>
        <body style="font-family:sans-serif; text-align:center; padding:40px;">
            <h1>🔥 My Private AI Engine</h1>
            <input id="input" style="width:80%; padding:10px;" placeholder="Ask anything..." />
            <br><br>
            <button onclick="send()">Send</button>
            <pre id="output" style="margin-top:20px;"></pre>

            <script>
                async function send() {
                    let input = document.getElementById("input").value;
                    let res = await fetch("/ask", {
                        method: "POST",
                        headers: {"Content-Type": "application/json"},
                        body: JSON.stringify({message: input})
                    });
                    let data = await res.json();
                    document.getElementById("output").innerText = data.response;
                }
            </script>
        </body>
    </html>
    """

@app.post("/ask")
async def ask(prompt: Prompt):
    response = client.responses.create(
        model="gpt-4.1-mini",
        input=prompt.message
    )
    return {"response": response.output_text}
