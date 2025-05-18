from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/chat")
async def chat_endpoint(message: str = Form(...)):
    # Simulated LLM response (you can replace with actual OpenAI call)
    response = f"🤖 Echoing: {message[::-1]}"
    return {"response": response}

if __name__ == '__main__':
    import uvicorn

    uvicorn.run("main:app", host = "127.0.0.1", port = 8000, reload = True)
    # In cmd: uvicorn main:app --host 127.0.0.1 --port 8000 --reload