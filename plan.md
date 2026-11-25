---
title: KisanSaathi MVP — weather-to-irrigation advisory
status: in-progress
created: 2026-11-25
updated: 2026-11-25
model: deepseek-v4-flash
---

# KisanSaathi MVP — weather-to-irrigation advisory

Hindi-first web app for Indian farmers: pick district, crop, sowing date → get a concrete irrigation decision ("irrigate today: 32 mm ≈ 1,30,000 L/acre" or "skip, rain in 2 days"), with the weather that drove it and a Hindi explanation.

**Core rule: the LLM never computes the recommendation — it only narrates a number the deterministic engine already produced.** `irrigation.py` is pure Python (simplified FAO-56 water balance), testable with no network. Hindi narration falls back to a template if no key/latency/rate limit, so the demo cannot fail on a network dependency. Hallucinated agronomic advice is real harm, and a network call in the critical path is how hackathon demos die.

Engine: ETc = Kc × ET0; Dr(i) = Dr(i-1) − effective_rain + ETc; TAW = (FC−WP)×root_depth, RAW = 0.5×TAW; irrigate when Dr ≥ RAW, gross = net/0.7. Output in mm and litres (1 mm/acre ≈ 4,047 L). Soil defaults to loam, shown as visible assumption chips.

Stack: React+Vite+Tailwind → FastAPI → Open-Meteo (no API key needed) → Supabase (profiles, advice log; in-memory fallback when no credentials) → Hindi narration (template first, optional LLM polish).

Open-Meteo field names could not be verified in plan mode; step 5 confirms them live, with a Hargreaves ET0 fallback if absent.

Cut line after step 10 — still a working end-to-end hero workflow on localhost.

## Steps

- [x] 1. Verify toolchain (`node -v`, `npm -v`, `python3 -V`); record actual versions.
- [ ] 2. Scaffold `backend/` + `frontend/`, `.gitignore`, `README.md`; one initial commit.
- [ ] 3. `design-tokens.css` from get_design_starter, edited to an agricultural palette (deep green + ochre) with a Hindi+Latin typeface; check_contrast every pair, light and dark.
- [ ] 4. FastAPI skeleton `backend/app/main.py` + `config.py` + `GET /health` + `requirements.txt`; verify with uvicorn.
- [ ] 5. `services/openmeteo.py`: India-restricted geocoding, 7-day daily forecast, field names confirmed live, 10-min cache, Hargreaves fallback; `/api/locations/search`, `/api/weather`.
- [ ] 6. `services/irrigation.py` pure functions (no I/O) + Kc table in `crops.py`; returns decision plus per-day trace so the UI can show why.
- [ ] 7. `tests/test_irrigation.py` table-driven (rain suppresses, dry spell triggers, stage changes amount, depletion never negative) + TestClient smoke test; run `pytest -q`.
- [ ] 8. `POST /api/advice` wiring profile + weather → engine → JSON; `models/schemas.py` contract.
- [ ] 9. `services/hindi.py`: deterministic Hindi template that always works, optional LLM polish on top; `/api/explain` returns Hindi + English fallback.
- [ ] 10. Store interface (`base.py`/`memory.py`/`supabase_store.py`) + `supabase/schema.sql` (`farms`, `advice_log`), service key server-side only; verify without credentials then with.
- [ ] 11. Frontend scaffold: Vite+React+Tailwind, `/api` proxy, `lib/api.js`, index.html linking `/design-tokens.css`; confirm proxy hits real backend.
- [ ] 12. UI: LocationPicker, CropSelect + sowing date, AdviceCard (action, mm + litres, assumption chips), WeatherStrip, HindiPanel with hi-IN Web Speech degrading to text.
- [ ] 13. End-to-end browser pass: Patna → wheat → advice → speaks → strip matches API; fix real breakage.
- [ ] 14. Write `COVEXCODE.md` from verified facts only: real tested commands, engine-computes/LLM-narrates rule, pure-function convention, env vars, confirmed API fields.

## Not doing

- Auth / multi-user — one seeded demo farmer keyed by session id.
- Offline / PWA — needs service workers + cached forecasts; roadmap, not faked.
- Any ML training — published water-balance agronomy beats a model trained on nothing in 8 hours.
- Languages beyond Hindi — config-shaped extension, not five template sets.
- SMS / IVR alerts — highest real impact, needs telco + scheduler; roadmap.
- Mandi prices / input shopping — in the track text but not the priority.
- Frontend unit tests — browser pass catches more; agronomy fully tested.
- Production hardening — rate limiting, RLS, migrations; fine for a demo laptop, dishonest for real use.

