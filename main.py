from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from openai import OpenAI
import os

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


class Prompt(BaseModel):
    message: str


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/chat")
async def chat(prompt: Prompt):
    user_message = prompt.message.strip()

    if not user_message:
        return JSONResponse({
            "reply": "Say something and I’ll reply.",
            "sources": []
        })

    try:
        response = client.responses.create(
            model="gpt-4.1-mini",
            input=user_message
        )

        reply_text = ""

if hasattr(response, "output") and response.output:
    for item in response.output:
        if hasattr(item, "content"):
            for content in item.content:
                if hasattr(content, "text"):
                    reply_text += content.text

        return JSONResponse({
            "reply": reply_text,
            "sources": []
        })

    except Exception as e:
        return JSONResponse(
            {
                "reply": f"Error talking to the AI: {str(e)}",
                "sources": []
            },
            status_code=500
        )
