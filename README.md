# Swish Support System

AI-powered customer support chat for Swish food delivery.

## Quick Start

### 1. Start Infrastructure + Services
```bash
./start.sh
```

This starts:
- PostgreSQL (port 5432)
- Redis (port 6379)
- Go Backend (port 8080)
- Python Agent (port 8001)

### 2. Start Web UI (separate terminal)
```bash
cd web
npm install  # first time only
npm run dev
```

Web UI runs on http://localhost:3000

### 3. Stop Everything
```bash
./stop.sh
```

## Project Structure

```
swishagent/
├── agent_service.py     # Python agent
├── main.go              # Go API
├── tools.py             # Agent tools
├── llm_client.py        # LLM client
├── rules.py             # Rule enforcement
├── start.sh             # Start services
├── stop.sh              # Stop services
├── test_agent.sh        # Test script
├── web/                 # React UI
├── docs/                # Documentation
└── docker-compose.yml   # Infrastructure
```

## Development

**Backend:**
```bash
python agent_service.py  # Start agent
go run main.go          # Start API
```

**Frontend:**
```bash
cd web
npm run dev
```

**Tests:**
```bash
./test_agent.sh
```

## Documentation

- [Business Rules](docs/agent_rules.md) - Agent behavior rules
- [Product Requirements](docs/prd.md) - PRD
- [Tech Stack](docs/tech.md) - Architecture
- [Architecture Analysis](docs/ARCHITECTURE_ANALYSIS.md) - Production readiness

## Environment Variables

Copy `.env.example` to `.env` and configure:
```bash
DB_URL=postgres://postgres:postgres@localhost:5432/swishagent?sslmode=disable
REDIS_ADDR=localhost:6379
AGENT_SERVICE_URL=http://localhost:8001
PORT=8080
```

Optional Langfuse tracing:
```bash
LANGFUSE_ENABLED=1
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_HOST=https://cloud.langfuse.com
```

If the Langfuse keys are missing, the agent continues with local JSON logs only.

## Deployment

```bash
./deploy.sh  # Start infrastructure
```

For production deployment, see [docs/tech.md](docs/tech.md).
