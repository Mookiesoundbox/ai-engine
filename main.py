from fastapi import FastAPI
from fastapi.responses import HTMLResponse

app = FastAPI()

@app.get("/", response_class=HTMLResponse)
def home():
    return """
    <html>
        <head>
            <title>My AI Engine</title>
        </head>
        <body style="font-family: sans-serif; text-align: center; margin-top: 50px;">
            <h1>🔥 My Private AI Engine</h1>
            <p>Search + AI coming online...</p>
        </body>
    </html>
    """
