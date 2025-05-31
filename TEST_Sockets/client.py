import asyncio
import websockets
import time

SERVER_WS_URL = "ws://localhost:8000/ws/ingest-logs"
LOG_FILE_PATH = "client_logs.txt"  # lub użyj None, by generować dynamicznie

async def send_logs():
    async with websockets.connect(SERVER_WS_URL) as websocket:
        print("Connected to server.")
        
        if LOG_FILE_PATH:
            # Tryb: wysyłaj linie z pliku logów
            with open(LOG_FILE_PATH, "r") as log_file:
                log_file.seek(0, 2)  # Przejdź na koniec
                while True:
                    line = log_file.readline()
                    if line:
                        await websocket.send(line.strip())
                        print(f"Sent: {line.strip()}")
                    else:
                        await asyncio.sleep(1)
        else:
            # Tryb: generuj logi dynamicznie
            counter = 1
            while True:
                log_line = f"[INFO] Generated log line #{counter}"
                await websocket.send(log_line)
                print(f"Sent: {log_line}")
                counter += 1
                await asyncio.sleep(2)

if __name__ == "__main__":
    try:
        asyncio.run(send_logs())
    except KeyboardInterrupt:
        print("Stopped by user.")
