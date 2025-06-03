# 🤖 AI Agent for Application Log Analysis

AI-powered agent that analyzes application logs in real time, detects anomalies, notify user, suggests fixes and helps to solve problems. Supports both local (via [Ollama](https://ollama.com)) and API-based LLMs. Includes an interactive web interface and provides integration with existing monitoring tools to streamline issue diagnosis and resolution.

---

## 📌 Key Features (WIP)

- **Real-time** Real time analyze done by AI Agent powered by LLMs (OpenAI, Anthropic, DeepSeek, etc. - model agnostic)
- **Interactive UI chat interface**
- **Access via API** FastAPI entpoints
- **Persistent chat history** stored in database
- **Responce validation** using Pydantic & PydanticAI models
- **Asynchronous backend** with FastAPI and asyncpg
- **Observability** via Logfire spans and tracing

---

## 📦 Project Structure (WIP)

```
BACKEND/
├── main.py                # FastAPI app entry point
├── schemas.py             # Pydantic models for chat/logs
├── utilslib.py            # Log parsing and validation utilities
├── LLM_Agents/
│   └── agentslib.py       # LLM agents & system prompt logic
├── Mock_UI/
│   ├── chat_app.html      # Simple HTML UI
│   └── chat_app.ts        # TypeScript frontend logic
├── Postgres_DB/
│   ├── initdb17/          # Docker Compose & init scripts
│   └── DB_PG17.py         # Async PostgreSQL connection & logic
├── sample.env             # Example environment config
└── ...
```

---

## 🚀 How to Run:

1. **Clone the repository**

   ```bash
   git clone https://github.com/el-arma/AGH_diploma
   cd AGH_diploma

   ```

2. **Prep .venv (for uv)**

   ```bash
   uv venv
   .venv\Scripts\activate
   uv sync

   ```

3. **Set up PostgreSQL Container DB**

   ```bash
   cd Postgres_DB\initdb17
   docker compose up -d

   ```

   \*\* REDIS SHORT TERM DB and BE SURE TO FIRST RUN:

   ```
    # Docker Container in demon mode:
    # in cmd: docker run -d --name redis-stack -p 6379:6379 redis/redis-stack-server:latest
   ```

4. **Check if database `chat_hist_db` is available (Optional)**

5. **Configure environment variables - IMPORTANT!**

   Repacel _sample.env_ file with proper _.env_ containing OPEN*API_KEY (optionally ANTHROPIC_API_KEY, but then change model in \_agentslib.py* settings)

6. **Run the application**

   ```bash
   uvicorn main:app --host 127.0.0.1 --port 8000 --reload
   ```

   in demon mode

   ```
   uvicorn main:app --host 127.0.0.1 --port 8000 --reload > ../uvicorn.log 2>&1 &
   ```

   Stop applications if needead

   ```
   lsof -i :8000
   kill -9
   ```

   Open your browser: [http://127.0.0.1:8000](http://127.0.0.1:8000)

7. **POST log to _/logs/ingest_ endpoint and refresh UI web page (Optional)**

   ***

## 🔌 API Endpoints

| Method | Endpoint       | Description                                                                            |
| ------ | -------------- | -------------------------------------------------------------------------------------- | --- |
| GET    | `/chat/`       | Retrieve chat history from db <br /> **(main endpoint for FrontEnd)**                  |
| POST   | `/chat/`       | Send messagea to a chat (streams replies) <br /> **(main endpoint for FrontEnd)**      |
| POST   | `/logs/ingest` | Submit logs for async LLM analysis <br /> **(str logs can be sent for this endpoint)** |     |

---

## ⚙️ Tech Stack

- **[FastAPI](https://fastapi.tiangolo.com/)** – Async Python web framework
- **[PydanticAI](https://ai.pydantic.dev/)** – Main AI Agent Framework
- **[PostgreSQL 17](https://www.postgresql.org/)** – Main DB
- **[asyncpg](https://magicstack.github.io/asyncpg/)** – Fast PostgreSQL driver
- **[Pydantic](https://docs.pydantic.dev/)** – Data validation & parsing
- **[Logfire](https://logfire.dev/)** – Observability and tracing
- **[OpenAI](https://platform.openai.com/)** / **[Anthropic](https://www.anthropic.com/)** – LLM integrations
- **[Ollama](https://ollama.com)** (WIP) – Local LLM

---

## 🧩 Customization

- You can change the LLM model in `LLM_Agents/agentslib.py`
- DB settings in `DB_PG17.py`
- Extend schemas in `schemas.py` to match your data structures

---

## 🥊 Development Notes

- All DB operations are fully **asynchronous** (max. 10 pools at onece, the pool is re-used)
- Log analysis is handled as **background tasks**
- **Logfire spans** help trace DB and AI Agent actions

---
