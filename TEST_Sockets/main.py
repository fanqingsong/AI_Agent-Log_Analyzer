from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from typing import List
import datetime

app = FastAPI()


active_connections: List[WebSocket] = []

@app.websocket("/ws/ingest-logs")
async def receive_logs(websocket: WebSocket):
    await websocket.accept()
    active_connections.append(websocket)
    client = websocket.client
    print(f"[+] Client connected: {client.host}:{client.port}")
    
    try:
        while True:
            log_line = await websocket.receive_text()
            timestamp = datetime.datetime.now().isoformat()
            formatted_log = f"{timestamp} - {client.host}:{client.port} - {log_line}"
            
            print(formatted_log)
            
            with open("received_logs.txt", "a") as f:
                f.write(formatted_log + "\n")

    except WebSocketDisconnect:
        print(f"[-] Client disconnected: {client.host}:{client.port}")
        active_connections.remove(websocket)

    except Exception as e:
        print(f"[!] Error: {e}")
        if websocket in active_connections:
            active_connections.remove(websocket)
        await websocket.close()


if __name__ == '__main__':
    import uvicorn

    uvicorn.run("main:app", host = "127.0.0.1", port = 8000, reload = True)

    # in cmd: uvicorn main:app --host 127.0.0.1 --port 8000 --reload
