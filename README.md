# KisanSaathi

Hindi-first advisory tool for Indian farmers. Pick a district, a crop and a sowing date and get a
concrete irrigation decision — *"irrigate today: 32 mm ≈ 1,30,000 litres/acre"* or *"skip it, rain
in two days"* — together with the weather that drove the answer and a Hindi explanation.

Built for HACKNOVA 2026, track: Agriculture and Rural Livelihoods.

## Architecture rule

**The language model never computes the recommendation.** A deterministic water-balance engine
produces the number; the narration layer only explains it. If the narration layer fails, a Hindi
template takes over and the advice is unchanged.

## Layout

```
backend/    FastAPI service — weather fetch, irrigation engine, narration, storage
frontend/   React + Vite + Tailwind UI
```

## Run

Backend (port 8000):

```sh
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn app.main:app --reload
```

Frontend (port 5173, proxies `/api` to the backend):

```sh
cd frontend
npm install
npm run dev
```

Tests:

```sh
cd backend
.venv/bin/pytest -q
```

## Configuration

Backend reads environment variables (see `backend/app/config.py`). All have working defaults for a
local demo:

| Variable | Used for | Without it |
|---|---|---|
| `SUPABASE_URL` | farm + advice storage | in-memory store |
| `SUPABASE_KEY` | Supabase service key (server-side only) | in-memory store |
| `OPENAI_API_KEY` | optional Hindi narration polish | template narration |
