# KisanSaathi

Hindi-first irrigation advisory for Indian farmers (HACKNOVA 2026, Agriculture track). Farmer picks
district + crop + sowing date; the app returns a concrete decision ("irrigate today: 32 mm") with the
forecast that drove it and a Hindi explanation. FastAPI backend, React+Vite frontend.

**Hard rule:** the language model never computes the recommendation. A deterministic water-balance
engine produces the number; narration only explains it. If narration fails, a Hindi template takes
over and *the advice is unchanged*. Never let a network call sit in the critical path.

## Layout

```
backend/app/main.py            FastAPI app: /health, /api/locations/search, /api/weather
backend/app/config.py          Settings (plain class, os.getenv at import), settings singleton
backend/app/models/schemas.py  Pydantic contracts — the single JSON shape the UI consumes
backend/app/services/openmeteo.py  Geocoding (countryCode=IN) + daily forecast, 10-min in-process cache, Hargreaves ET0 fallback
backend/app/store/             empty — store layer not built yet
backend/tests/                 empty — no tests written yet
frontend/index.html            links /design-tokens.css; entry /src/main.jsx
frontend/src/App.jsx           placeholder ("UI lands in step 12")
frontend/public/design-tokens.css  the one styling source (127 custom properties, light+dark)
plan.md                        living roadmap with step checkboxes
```

## Commands (verified)

```sh
cd backend && .venv/bin/uvicorn app.main:app --reload   # serves :8000; /health returns {"status":"ok",...}
cd backend && .venv/bin/pytest -q                       # currently collects 0 tests, exits 5
```

Backend venv is already built with `fastapi 0.165.0`, `httpx 0.28.1`, `pytest 9.2.0` (Python 3.15.2).
Only re-create it if missing. The three endpoints work live against Open-Meteo; bad query params
return 422 and upstream failures return 502.

**The frontend does not run yet.** `frontend/package.json` declares no dependencies and there is no
`vite.config.js`, so `npm run build` fails with `vite: command not found`, and the README's "/api
proxied to the backend" is not implemented — that config still has to be written. Node v24.12.0,
npm 11.6.2 are installed.

## Conventions

- `irrigation.py` / `crops.py` (not written yet) must be **pure functions, no I/O**, so agronomy is
  testable without network. Tests are table-driven; frontend has no unit tests (browser pass instead).
- Every setting in `config.py` needs a working default — the app must start with zero env vars and
  degrade (memory store, template narration) rather than fail. `Settings` reads `os.getenv` when the
  class body executes at import, so set env vars *before* importing `app.config`.
- Renaming a field in `schemas.py` is a visible API change, not a silent one.
- Upstream failure becomes `502`, never an empty list: the UI must tell "no such village" from
  "weather service is down". Missing/null `ET0` falls back to Hargreaves — never return zero water
  demand, which would produce dangerous "no need to irrigate" advice.
- Styling: read tokens from `design-tokens.css`; never hardcode a colour in a component. Green
  (`--accent`) is the single primary action colour; ochre is decorative, `--warning` is its
  contrast-safe wording. Typefaces are Devanagari-first (Tiro Devanagari Hindi + Mukta). Every page
  must `<link rel="stylesheet" href="/design-tokens.css">` — leading slash. Re-check any new
  pairing with contrast before shipping.
- Modules carry a docstring explaining *why* the design is what it is (especially the LLM rule).
  Match that.
- `plan.md` is the roadmap: check a step's box only when it is actually verified, and prefer the code
  over the checkboxes — step 5 is still unchecked although `openmeteo.py` is finished and working.
