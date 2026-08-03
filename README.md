# Market Attribution Dashboard

Explains **why an ETF moved today** by ranking each holding's contribution to the index return.

```
Contribution (pp) = Weight (%) × Daily Return (%)  / 100
```

Stocks are sorted by **absolute contribution** — a stock moving 10% with a 0.5% weight matters
less than one moving 2% with an 8% weight.

Supports: **QQQ** (Invesco NASDAQ-100), **VOO** (Vanguard S&P 500), **SCHD** (Schwab Dividend).

---

## Features

- Daily and intraday (live) attribution breakdown per ETF
- Date range view — pick any start/end date to see cumulative contributors
- Sector-level aggregation
- Auto-refresh every 30 min during market hours, pauses when tab is hidden
- Startup backfill — automatically fills missing days when the app restarts
- Rule-based text summary of the day's market moves

---

## Quick Start (local development)

### Prerequisites

| Tool | Version | Install |
|------|---------|---------|
| Python | 3.12 | `brew install python@3.12` |
| Node.js | 22 | `brew install node` |
| Docker | optional | Docker Desktop — only needed for deployment |

### 1. Clone and configure

```bash
git clone <your-repo-url> etfContributerAnalyser
cd etfContributerAnalyser

cp .env.example .env   # defaults work out of the box
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
cd frontend
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

On first startup the backend will automatically backfill the last 30 days of data.

**Terminal 2 — Frontend (Next.js)**
```bash
cd frontend
npm run dev
# → http://localhost:3000
```

### 5. Run tests

```bash
cd backend
source .venv/bin/activate
pytest -v
```

---

## Deployment (Docker — Ubuntu / Linux laptop)

### Install Docker

```bash
sudo apt update
sudo apt install -y docker.io docker-compose-v2

# Allow running docker without sudo
sudo usermod -aG docker $USER
newgrp docker

# Verify
docker --version
docker compose version
```

### First-time deploy

```bash
# 1. Copy the project to the server (from your dev machine)
rsync -avz --exclude 'node_modules' --exclude '.venv' --exclude '*.db' \
  /path/to/etfContributerAnalyser/ \
  user@<server-ip>:~/etfContributerAnalyser/

# 2. On the server
cd ~/etfContributerAnalyser
cp .env.example .env          # defaults are fine — edit if needed

# 3. Build and start (takes 2–3 min on first build)
docker compose up --build -d
```

### Verify it's running

```bash
# Check both containers are healthy
docker compose ps

# Watch the startup backfill logs
docker compose logs -f backend
# Look for: "Startup backfill complete."

# Health check
curl http://localhost:8888/api/health
```

App is available at `http://localhost:3000` or `http://<server-ip>:3000` from other devices on the network.

### Survive reboots

```bash
# Enable Docker to start on boot
sudo systemctl enable docker
sudo systemctl enable containerd
```

Both containers have `restart: unless-stopped` — they come back automatically after a reboot.
The startup backfill fills any gap since the last run.

### Useful Docker commands

```bash
# View live logs
docker compose logs -f

# Stop everything
docker compose down

# Restart a single container
docker compose restart backend

# Backup the SQLite database
docker compose cp backend:/app/data/market_attribution.db ./backup.db
```

---

## Deploying Updates

### Option 1 — rsync (recommended, no GitHub needed)

Sync only changed files from your dev machine to the server:

```bash
rsync -avz --exclude 'node_modules' --exclude '.venv' --exclude '*.db' \
  /path/to/etfContributerAnalyser/ \
  user@<server-ip>:~/etfContributerAnalyser/
```

Then on the server, rebuild and restart:

```bash
docker compose up --build -d
```

If only backend Python files changed (no dependency changes), you can rebuild just the backend:

```bash
docker compose up --build -d backend
```

### Option 2 — scp (for single file changes)

```bash
# Copy one file
scp backend/src/api/routes/attribution.py \
  user@<server-ip>:~/etfContributerAnalyser/backend/src/api/routes/

# Then on the server
docker compose restart backend
```

### Option 3 — GitHub (cleanest long-term)

```bash
# Dev machine
git push origin main

# Server
git pull
docker compose up --build -d
```

---

## Manual Data Management

On first startup the app automatically backfills the last 30 days (configurable via `BACKFILL_DAYS`).
For manual control:

```bash
# Backfill last N days for all ETFs
curl -X POST "http://localhost:8888/api/admin/backfill?days=30"

# Backfill a specific ETF only
curl -X POST "http://localhost:8888/api/admin/backfill?symbol=QQQ&days=7"

# Check what data is in the database
curl http://localhost:8888/api/admin/status
```

---

## Environment Variables

See `.env.example` for all options. Key settings:

| Variable | Default | Description |
|----------|---------|-------------|
| `DATA_PROVIDER` | `yfinance` | Price source: `yfinance` (free) or `fmp` |
| `FMP_API_KEY` | _(blank)_ | Required only if `DATA_PROVIDER=fmp` |
| `SCHEDULE_TIME` | `16:15` | Daily update time (US/Eastern, 24h) |
| `BACKFILL_DAYS` | `30` | Days of history to load on first startup |
| `LOG_LEVEL` | `INFO` | `DEBUG` \| `INFO` \| `WARNING` \| `ERROR` |

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/health` | Health check |
| `GET` | `/api/etfs` | List supported ETFs |
| `GET` | `/api/attribution/{symbol}` | Daily attribution (latest or `?date=YYYY-MM-DD`) |
| `GET` | `/api/attribution/{symbol}/live` | Intraday attribution (falls back to close outside market hours) |
| `GET` | `/api/attribution/{symbol}/range` | Cumulative attribution over a date range (`?start=&end=`) |
| `GET` | `/api/attribution/{symbol}/available-dates` | Dates that have data in the DB |
| `GET` | `/api/summary/{symbol}` | Rule-based text summary |
| `POST` | `/api/admin/backfill` | Trigger data backfill (`?days=N&symbol=X`) |
| `GET` | `/api/admin/status` | Database contents summary |

Interactive API docs: `http://localhost:8888/docs`

---

## Project Structure

```
etfContributerAnalyser/
├── backend/
│   ├── src/
│   │   ├── api/routes/       # FastAPI endpoint handlers
│   │   ├── core/             # Attribution engine, summary generator, market hours
│   │   ├── providers/        # Data sources (yfinance, FMP, holdings parsers)
│   │   ├── models/           # SQLAlchemy models + database session
│   │   ├── scheduler/        # Daily job + startup backfill (APScheduler)
│   │   └── config.py         # Settings (pydantic-settings)
│   ├── tests/                # Pytest unit tests
│   ├── main.py               # FastAPI app entry point
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── app/              # Next.js App Router pages
│   │   ├── components/       # ETFDashboard, ContributorTable, SectorSummary,
│   │   │                     # DateRangePicker, DataFreshnessTag
│   │   └── lib/              # API client, TypeScript types
│   ├── public/
│   ├── package.json
│   └── Dockerfile
├── docker-compose.yml
├── .env.example
└── README.md
```

---

## Design Principles

1. **Contribution over return** — rank by `weight × return`, not raw return
2. **Data freshness is visible** — always show when data was last updated
3. **Graceful degradation** — stale data beats no data; shown with a warning
4. **Free by default** — yfinance requires no API key
5. **Simple deployment** — one `docker compose up -d` to start everything
