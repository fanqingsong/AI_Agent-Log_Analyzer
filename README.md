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
AI_Agent-Log_Analyzer/
├── app/                          # Backend (FastAPI application, split by service)
│   ├── main.py                   # App entry: lifespan, router wiring, static mount
│   ├── config.py                 # Centralized env-var configuration
│   ├── deps.py                   # Shared FastAPI dependencies (db, redis, agent)
│   ├── chat/                     # Chat service (conversation + model switching)
│   │   ├── routes.py             #   /chat/, /chat/delete, /set_model/
│   │   ├── service.py            #   message conversion + streaming
│   │   ├── repository.py         #   async PostgreSQL persistence (ChatDB)
│   │   ├── schemas.py            #   ChatMessage, ChatDeleteRequest
│   │   └── initdb17/init_db.sql  #   DB initialization script
│   ├── logs/                     # Log analysis service (ingest + simulator)
│   │   ├── routes.py             #   /logs/ingest, /logs/sources, /logs/simulate
│   │   ├── service.py            #   process_single_log + LLM analysis
│   │   ├── repository.py         #   async Redis short-term storage
│   │   ├── simulator.py          #   sample log replay engine
│   │   ├── parsing.py            #   log parsing, formatting, Discord notify
│   │   └── schemas.py            #   MockKafkaLogEntry
│   └── llm/                      # Shared LLM capability
│       └── agent.py              #   LogAgent (model configs + hot-swap)
├── frontend/                     # Frontend (browser UI)
│   ├── chat_app.html             # HTML frontend
│   ├── chat_app.ts               # TypeScript frontend logic
│   └── styles.css                # UI styles
├── test_logs/                    # Sample Kafka logs (bundled into the image)
│   ├── deanonymized_server.log
│   └── deanonymized_server_backup.log
├── grafana/                      # Prometheus/Grafana config (optional monitoring profile)
│   ├── prometheus.yml
│   ├── node_exporter/
│   ├── LICENSE
│   └── NOTICE
├── pyproject.toml                # Python project config
├── uv.lock                       # uv dependency lock file
├── Dockerfile                    # Builds the FastAPI app image
├── docker-compose.yml            # Unified stack: app + postgres + redis (+ monitoring)
├── sample.env                    # Example environment config
├── BUSINESS_LOGIC.md             # Business logic documentation (Mermaid diagrams)
└── README.md                     # This file
```
---

## 🚀 How to Run

### Option A — Docker Compose (recommended)

The whole stack (FastAPI app + PostgreSQL + Redis, and optionally the Grafana monitoring stack) is orchestrated by a single `docker-compose.yml` at the project root.

1. **Configure environment variables**
   ```cmd
   cp sample.env .env
   ```
   Edit `.env` and fill in your LLM API keys (e.g. `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`). All other values have sensible defaults.

2. **Start the core services** (app + PostgreSQL + Redis)
   ```cmd
   docker compose up -d --build
   ```

3. **(Optional) Start the Grafana / Prometheus monitoring stack**
   ```cmd
   docker compose --profile monitoring up -d --build
   ```

4. **Open the app**
   - UI:        [http://127.0.0.1:8000](http://127.0.0.1:8000)
   - Grafana:   [http://127.0.0.1:3000](http://127.0.0.1:3000)
   - Prometheus:[http://127.0.0.1:9090](http://127.0.0.1:9090)

5. **Common commands**
   ```cmd
   docker compose logs -f app       # follow app logs
   docker compose restart app       # restart after editing .env
   docker compose down              # stop everything (keeps volumes)
   docker compose down -v           # stop and DELETE database data
   ```

> 💡 The compose file uses the Huawei Cloud CN image mirror prefix
> (`swr.cn-north-4.myhuaweicloud.com/ddn-k8s/docker.io/`) on every image to
> speed up pulls from inside mainland China. Remove the prefix if you are
> outside CN.

---

### Option B — Run locally (without Docker)

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

3. **Start PostgreSQL and Redis** (managed by the root `docker-compose.yml`)
   ```cmd
   docker compose up -d postgres redis
   ```

4. **Start Redis (short-term log storage)**
   ```cmd
   docker run -d --name redis-stack -p 6379:6379 redis/redis-stack-server:latest
   ```

5. **Configure environment variables**
   - Copy `sample.env` to `.env` and fill in your API keys.
   - For local Ollama, set `LOCAL_MODEL_URL=http://localhost:11434/v1`.

6. **(Optional) Run Grafana/Prometheus monitoring**
   ```cmd
   docker compose --profile monitoring up -d
   ```

7. **Run the application**
   ```cmd
   uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
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

- Change LLM model in `app/llm/agent.py`
- DB settings in `app/config.py`
- Extend schemas in `app/chat/schemas.py` and `app/logs/schemas.py` to match your data structures

---

## 🥊 Development Notes

- All DB operations are fully **asynchronous**
- Log analysis is handled as **background tasks**
- **Logfire spans** help trace DB and AI Agent actions
---
