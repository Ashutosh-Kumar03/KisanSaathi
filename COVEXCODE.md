# KisanSaathi

Hindi-first irrigation advisory for Indian farmers (HACKNOVA 2026, Agriculture track). Farmer picks
village + crop (wheat or rice) + sowing date; the app returns one decision — irrigate today, or wait —
with the water amount in mm and litres/acre, a Hindi sentence, spray and urea guidance, the forecast
that drove it, and the citations behind every number. FastAPI backend, React+Vite frontend.

**Hard rule:** the recommendation is computed by deterministic code, never by a language model.
`services/irrigation.py` is pure (no I/O at all), so the rule is enforced by construction rather than
by discipline. Narration (`services/narration.py`) formats numbers it is handed and cannot compute
one. There is no LLM in the app; a network call never sits in the critical path.

## Layout

```
backend/app/main.py             /health, /api/locations/search, /api/weather, POST /api/advice
backend/app/config.py           Settings (plain class, os.getenv at import), settings singleton
backend/app/data/crop_rules.py  THE crop data file: wheat + rice stages, Kc, root depth, p, spray/urea
                                thresholds — every value carries its own `source` string
backend/app/services/irrigation.py  pure FAO-56 water balance; returns Advice + per-day trace
backend/app/services/narration.py   Hindi/English templates (no LLM), lakh-grouped figures
backend/app/services/openmeteo.py   geocoding (countryCode=IN) + daily forecast with past_days,
                                    10-min cache, Hargreaves ET0 fallback
backend/app/models/schemas.py   Pydantic contracts — the single JSON shape the UI consumes
backend/app/store/              empty — store layer never built (not needed; no persistence)
backend/tests/                  56 tests: irrigation, narration, api
frontend/vite.config.js         /api + /health proxy to BACKEND_URL (default 127.0.0.1:8000)
frontend/src/App.jsx            the single screen: village -> crop -> sowing date -> advice
frontend/src/components/        VillagePicker.jsx, AdviceCard.jsx
frontend/src/lib/               api.js (classified errors), speech.js, offline.js (localStorage)
frontend/src/styles/app.css     mobile-first, reads tokens only, no colour literals
frontend/public/design-tokens.css  the one styling source (127 custom properties, light+dark)
```

## Commands (verified)

```sh
cd backend && .venv/bin/uvicorn app.main:app --reload   # :8000
cd backend && .venv/bin/pytest -q                       # 56 passed
cd frontend && npm install && npm run dev               # :5173
cd frontend && npm run build                            # 157 kB js / 51 kB gzipped
```

Venv: `fastapi 0.165.0`, `httpx 0.28.1`, `pytest 9.2.0`, Python 3.15.2. Node v24.12.0, npm 11.6.2.
Only re-create the venv if missing. Endpoints verified live against Open-Meteo; 422 on bad input,
502 on upstream failure.

**Vite binds to `localhost` (IPv6) here, not `127.0.0.1`.** `http://localhost:5173` answers while
`http://127.0.0.1:5173` refuses — so a `curl 127.0.0.1:5173` returning `000` against a perfectly
healthy dev server is this, not a proxy bug. Use `localhost` when checking the frontend.

## Conventions

- `irrigation.py` stays **pure functions, no I/O** — that is what makes the agronomy testable without
  network and the no-LLM rule structural. Anything needing weather goes in `main.py`.
- The engine must be given real history (`get_forecast(past_days=...)`). Starting the balance at field
  capacity *today* means one day of demand can never reach the stress point, so the app could never
  justify irrigating. Observed past days from the same API, capped at 92.
- Decision uses depletion at the end of **today**, not at the end of the forecast week — otherwise dry
  days later in the week pull today's advice forward. (This was a real bug.)
- Every setting in `config.py` needs a working default; the app starts with zero env vars and degrades
  (memory store, template narration). `Settings` reads `os.getenv` at import, so set env vars *before*
  importing `app.config`.
- Upstream failure is `502`, never empty and never invented advice: the UI must tell "no such village"
  from "weather service is down", and "no answer" from "no need to irrigate". Missing/null ET0 falls
  back to Hargreaves — never zero water demand.
- **Citations:** FAO-56 Tables 11/12/22 for Kc, root depth, depletion and stage lengths; TNAU for
  wheat's critical windows only; rice cites FAO-56 alone. Thresholds with no published source are
  marked `OPERATIONAL` and shown to the farmer as assumptions. Two tests fail the build if any other
  citation appears. Never invent an ICAR/SAU citation to fill a slot.
- Renaming a field in `schemas.py` is a visible API change.
- Styling: read tokens from `design-tokens.css`; never hardcode a colour in a component. Green
  (`--accent`) is the single action colour; ochre is decorative, `--warning` is its contrast-safe
  wording. Devanagari-first typefaces. `/design-tokens.css` needs a leading slash. 44px touch targets.
- `AdviceCard` computes nothing itself — not even a percentage. Every figure is the backend's.
- Modules carry a docstring explaining *why* the design is what it is. Match that.
- `plan.md` checkboxes lag reality; prefer the code over the boxes.
