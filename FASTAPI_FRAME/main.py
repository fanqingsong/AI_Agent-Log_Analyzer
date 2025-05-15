from fastapi import FastAPI, Request
import uvicorn


app = FastAPI()

@app.get("/")
async def root():
    return {"message": "Hello there!"}

@app.post("/logs/ingest")
async def log_receiver(request: Request):
    raw_body = await request.body()
    log_text = raw_body.decode("utf-8")
    
    print(f"Received log: {log_text}")
    
    return {"status": "ok", "message": "Log received"}

# TO RUN MANUALLY: uvicorn main:app --reload

if __name__ == "__main__":
    uvicorn.run("main:app", host = "127.0.0.1", port = 8000, reload = True)
    
    