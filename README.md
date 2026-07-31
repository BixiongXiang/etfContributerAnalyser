# Market Attribution Dashboard

Explains **why an ETF moved today** by ranking each holding's contribution to the index return.

```
Contribution = Weight × Daily Return
```

Stocks are sorted by **absolute contribution** — a stock moving 10% with a 0.5% weight matters
less than one moving 2% with an 8% weight.

Supports: **QQQ** (Invesco NASDAQ-100), **VOO** (Vanguard S&P 500), **SCHD** (Schwab Dividend).

---

## Quick Start (local development)

### Prerequisites

| Tool | Version | Install |
|------|---------|---------|
| Python | 3.12 | `brew install python@3.12` |
| Node.js | 22 | `brew install node` |
| git | any | pre-installed on macOS |
| Docker | optional | Docker Desktop — only needed for deployment |

### 1. Clone and configure

```bash
git clone <your-repo-url> market-attribution
cd market-attribution

# Copy environment template (no edits needed for default yfinance setup)
cp .env.example backend/.env
```

### 2. Backend setup

```bash
cd backend
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Frontend setup

```bash
cd ../frontend
npm install
```

### 4. Run locally

Open two terminals:

**Terminal 1 — Backend (FastAPI)**
```bash
cd backend
source .venv/bin/activate
uvicorn main:app --reload --port 8888
```

On first startup the backend will:
1. Create `backend/data/market_attribution.db`
2. Seed the three ETF records

**Terminal 2 — Frontend (Next.js)**
```bash
cd frontend
npm run dev
# → http://localhost:3000
```

The frontend proxies `/api/*` to `localhost:8000`. Hot reload is enabled for both.

### 5. Run tests

```bash
cd backend
source .venv/bin/activate
pytest -v
```

---

## Production Deployment (Docker)

Docker is for deployment only — not required during development.

### Supported targets

- **Windows laptop** — Docker Desktop with Linux containers (default)
- **Amazon EC2 (Amazon Linux / Ubuntu)** — standard Docker Compose

### One-command startup

```bash
# In the project root
cp .env.example .env   # edit if needed
docker compose up -d
```

This starts:
- `backend` — FastAPI + APScheduler + SQLite
- `frontend` — Next.js (production build)

Open `http://localhost:3000` (local) or `http://<ec2-public-ip>:3000` (EC2).

### EC2 setup (one-time)

```bash
# Install Docker on Amazon Linux 2023
sudo yum update -y
sudo yum install -y docker
sudo systemctl start docker
sudo usermod -aG docker ec2-user

# Install Docker Compose plugin
sudo mkdir -p /usr/local/lib/docker/cli-plugins
sudo curl -SL https://github.com/docker/compose/releases/latest/download/docker-compose-linux-x86_64 \
     -o /usr/local/lib/docker/cli-plugins/docker-compose
sudo chmod +x /usr/local/lib/docker/cli-plugins/docker-compose

# Clone and start
git clone <your-repo-url> market-attribution
cd market-attribution
cp .env.example .env
docker compose up -d
```

### Persistent data

SQLite is stored in a Docker named volume (`db_data`). It survives container restarts.

```bash
# Backup the database
docker compose cp backend:/app/data/market_attribution.db ./backup.db

# View logs
docker compose logs -f backend
```

---

## Environment Variables

See `.env.example` for all options. Key settings:

| Variable | Default | Description |
|----------|---------|-------------|
| `DATA_PROVIDER` | `yfinance` | Price source: `yfinance` (free) or `fmp` |
| `FMP_API_KEY` | _(blank)_ | FMP key — only needed if `DATA_PROVIDER=fmp` |
| `SCHEDULE_TIME` | `16:15` | Daily update time (US/Eastern, 24h) |
| `BACKFILL_DAYS` | `30` | Days of history to load on first startup |
| `LOG_LEVEL` | `INFO` | `DEBUG` \| `INFO` \| `WARNING` \| `ERROR` |

---

## Project Structure

```
etfContributerAnalyser/
├── backend/
│   ├── src/
│   │   ├── api/routes/       # FastAPI endpoint handlers
│   │   ├── core/             # Attribution engine, summary generator
│   │   ├── providers/        # Data sources (yfinance, FMP, holdings parsers)
│   │   ├── models/           # SQLAlchemy models + database session
│   │   ├── scheduler/        # Daily job (APScheduler)
│   │   └── config.py         # Settings (pydantic-settings)
│   ├── tests/                # Pytest unit tests
│   ├── main.py               # FastAPI app entry point
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── app/              # Next.js App Router pages
│   │   ├── components/       # React components
│   │   └── lib/              # API client, TypeScript types
│   ├── package.json
│   └── Dockerfile
├── docker-compose.yml
├── .env.example
└── README.md
```

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/health` | Health check |
| `GET` | `/api/etfs` | List supported ETFs |
| `GET` | `/api/attribution/{symbol}` | Daily attribution (latest or `?date=YYYY-MM-DD`) |
| `GET` | `/api/attribution/{symbol}/history` | Historical (`?period=5d\|30d\|90d\|ytd`) |
| `GET` | `/api/summary/{symbol}` | Rule-based text summary |

Interactive API docs: `http://localhost:8000/docs`

---

## Implementation Status

- [x] Project scaffold (backend + frontend)
- [x] SQLite schema + SQLAlchemy models
- [x] yfinance price provider (batch mode)
- [x] Holdings parsers: QQQ (Invesco), VOO (Vanguard), SCHD (Schwab)
- [x] Attribution engine with unit tests
- [x] Rule-based summary generator
- [x] Daily scheduler (APScheduler + NYSE calendar)
- [x] Next.js frontend scaffold (ETF tabs, contributor table, sector bars)
- [ ] REST endpoint implementations (Week 2)
- [ ] End-to-end integration test (Week 2)
- [ ] Manual validation against live data (Week 3)

---

## Design Principles

1. **Contribution over return** — rank by `weight × return`, not raw return
2. **Data freshness is visible** — always show when data was last updated
3. **Graceful degradation** — stale data beats no data; show with a warning
4. **Free by default** — yfinance requires no API key
5. **Simple deployment** — one `docker compose up -d` to start everything
