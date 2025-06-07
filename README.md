# 🤖 AI Agent for Application Log Analysis

AI-powered agent that analyzes application logs in real time, detects anomalies, notifies users, suggests fixes, and helps solve problems. Supports both local (via [Ollama](https://ollama.com)) and API-based LLMs. Includes an interactive web interface and provides integration with monitoring tools to streamline issue diagnosis and resolution.

---

## 📌 Key Features

- **Real-time log analysis** powered by LLMs (OpenAI, Anthropic, DeepSeek, Ollama, etc.)
- **Interactive chat UI** (TypeScript/HTML frontend)
- **REST API** via FastAPI
- **Persistent chat history** in PostgreSQL
- **Log validation** using Pydantic & PydanticAI
- **Asynchronous backend** (FastAPI, asyncpg)
- **Observability** with Logfire
- **Short-term log storage** in Redis
- **Grafana/Prometheus** monitoring stack (optional)

---

## 📦 Project Structure

```
BACKEND/
├── main.py                      # FastAPI app entry point
├── schemas.py                   # Pydantic models for chat/logs
├── utilslib.py                  # Log parsing, validation, and utility functions
├── pyproject.toml               # Python project config
├── uv.lock                      # uv dependency lock file
├── sample.env                   # Example environment config
├── README.md                    # This file
├── LLM_Agents/
│   └── agentslib.py             # LLM agent logic, system prompts, tools
├── Mock_UI/
│   ├── chat_app.html            # HTML frontend
│   ├── chat_app.ts              # TypeScript frontend logic
│   └── styles.css               # UI styles
├── Mock_Services/
│   └── sent_logs.ipynb          # Notebook for mock log sending
├── Postgres_DB/
│   ├── DB_PG17.py               # Async PostgreSQL logic
│   └── initdb17/
│       ├── docker-compose.yml   # Docker Compose for PostgreSQL
│       └── init_db.sql          # DB initialization script
├── Redis_DB/
│   └── ST_DB_Redis.py           # Async Redis logic for log storage
├── grafana/
│   ├── docker-compose.yml       # Docker Compose for Grafana/Prometheus
│   ├── prometheus.yml           # Prometheus config
│   ├── node_exporter/           # Node exporter for metrics
│   ├── LICENSE
│   └── NOTICE
├── static/
│   └── styles.css               # Additional static styles
├── test_logs/
│   ├── deanonymized_server.log
│   └── deanonymized_server_backup.log
├── grafana/
│   ├── docker-compose.yml       # Docker Compose for Grafana/Prometheus
│   ├── prometheus.yml           # Prometheus config
│   ├── node_exporter/           # Node exporter for metrics
│   ├── LICENSE
│   └── NOTICE
```
---

## 🚀 How to Run

1. **Clone the repository**
   ```cmd
   git clone https://github.com/el-arma/AGH_diploma
   cd AGH_diploma
   ```

2. **Set up Python environment**
   ```cmd
   uv venv
   .venv\Scripts\activate
   uv sync
   ```

3. **Set up PostgreSQL**
   ```cmd
   cd Postgres_DB\initdb17
   docker compose up -d
   ```

4. **Set up Redis (short-term log storage)**
   ```cmd
   docker run -d --name redis-stack -p 6379:6379 redis/redis-stack-server:latest
   ```

5. **Configure environment variables**
   - Copy `sample.env` to `.env` and fill in your API keys (e.g., `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`).

6. **(Optional) Run Grafana/Prometheus monitoring**
   ```cmd
   cd grafana
   docker compose up -d
   ```

7. **Run the application**
   ```cmd
   uvicorn main:app --host 127.0.0.1 --port 8000 --reload
   ```

   Open your browser: [http://127.0.0.1:8000](http://127.0.0.1:8000)

---


## 🔌 API Endpoints:
### External (for users)
| Method | Endpoint         | Description                                                        |
|--------|------------------|--------------------------------------------------------------------|
| POST   | `/logs/ingest`   | Submit logs for async LLM analysis                                 |

### Internal (for internal system)
| Method | Endpoint         | Description                                                        |
|--------|------------------|--------------------------------------------------------------------|
| GET    | `/`              | Redirect to UI (main chat page)                                    |
| GET    | `/chat_app.ts`   | Download TypeScript frontend logic                                 |
| GET    | `/chat/`         | Retrieve chat history (main endpoint for frontend)                 |
| POST   | `/chat/`         | Send message to chat (streams LLM replies)                         |
| DELETE | `/chat/delete`   | Delete chat(s) by chatId                                           |
| POST   | `/set_model/`    | Change LLM model (OpenAI, Anthropic, DeepSeek, Ollama)             |

**Explanation:**
- **External** – endpoints for end users
- **Internal** – endpoints for system

---

## ⚙️ Tech Stack

- **FastAPI** – Async Python web framework
- **PydanticAI** – AI Agent Framework
- **PostgreSQL 17** – Main DB
- **asyncpg** – Fast PostgreSQL driver
- **Pydantic** – Data validation & parsing
- **Logfire** – Observability and tracing
- **OpenAI / Anthropic / DeepSeek / Ollama** – LLM integrations
- **Redis** – Short-term log storage
- **Grafana/Prometheus** – Monitoring stack

---

## 🧩 Customization

- Change LLM model in `LLM_Agents/agentslib.py`
- DB settings in `Postgres_DB/DB_PG17.py`
- Extend schemas in `schemas.py` to match your data structures

---

## 🥊 Development Notes

- All DB operations are fully **asynchronous**
- Log analysis is handled as **background tasks**
- **Logfire spans** help trace DB and AI Agent actions
---
