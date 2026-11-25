---
title: KisanSaathi one-screen irrigation advisor
status: in-progress
created: 2026-11-25
updated: 2026-11-25
base_commit: adf72c0
model: deepseek-v4-flash
---

# KisanSaathi one-screen irrigation advisor

Build the missing half of the app: the deterministic engine, the sourced crop-rule data file, a template narration layer, one `POST /api/advice` endpoint, and the single mobile-first screen that consumes it.

**Shape, and why:**

- **Crop rules in one Python module, not JSON.** You asked for a source comment per rule, and JSON cannot carry comments. `backend/app/data/crop_rules.py` holds every agronomic number for wheat and rice in two dicts, and each rule is a small object with its value *and* a `source` string — so the citation is machine-readable (it can render as a chip in the UI) as well as being a comment on the line.
- **The engine is a pure function, no I/O.** `advise(crop, sowing_date, forecast, today)` takes plain values and returns a decision plus the per-day trace. That keeps agronomy testable without a network and keeps the "LLM/network never computes the number" rule intact by construction — narration is a separate pure function that only formats numbers it is handed.
- **Narration is Hindi and English templates only, no LLM.** Deterministic strings, so there is no network call in the critical path and the English toggle is just a second template rather than a second subsystem.
- **No Tailwind.** `README.md` says "React + Vite + Tailwind" but nothing is installed and the token file already provides button/card/input/stat/chip classes. Plain CSS reading tokens is lighter on data and keeps the "never hardcode a colour" rule enforceable.
- **Offline = `localStorage`, not a service worker.** One screen, tight scope: the last advice survives an API/Open-Meteo failure and is shown with a stale timestamp. Be clear that the app shell itself still needs a network to load — a real offline app needs a service worker, which is out of scope.

**One thing to be straight about:** you asked for ICAR / state-university citations, and I will not invent one to fill a slot. The Kc values, root depth, depletion fraction and stage lengths I can cite exactly — FAO-56 (Allen et al. 1998), Table 12 and Table 22, which is what those numbers actually come from and is genuinely verifiable. ICAR/SAU citations get added only for specific published recommendations I can confirm in step 1 (the wheat first-irrigation-at-CRI-at-20–25-DAS kind of thing). Where a rule cannot be tied to a published source, it ships citing FAO-56 or is shown in the UI as a stated operational threshold — never as a fake citation, and never as a number with no origin.

## Steps

- [x] 1. Verify upstream before writing any rule: one live request to Open-Meteo for the daily wind fields the spray rule needs (`wind_speed_10m_max`, `wind_gusts_10m_max`) to confirm exact names, and confirm the FAO-56 wheat/rice Kc, root-depth and depletion values plus any ICAR/SAU recommendation I intend to cite. Record the confirmed field names in the docstring of `backend/app/services/openmeteo.py`. Nothing downstream starts until this is real.
- [x] 2. Create `backend/app/data/crop_rules.py` — the single data file. WHEAT and RICE dicts: stage lengths in days from sowing, Kc per stage, root depth, depletion fraction, critical irrigation stages, per-event application efficiency, and the spray/fertiliser thresholds (rain mm, wind km/h). Every rule carries a `source` field and an inline comment; a module docstring lists the references once.
- [x] 3. Create `backend/app/services/irrigation.py` — pure functions, no I/O. FAO-56 single-Kc water balance: ETc = Kc x ET0, Dr(i) = Dr(i-1) - effective_rain + ETc, TAW = (FC-WP) x root_depth, RAW = p x TAW, irrigate when Dr >= RAW; net mm, gross = net / efficiency, litres = mm x 4047. Warnings for spray and urea derived from the next 24-48h rain and wind. Returns action, stage, mm, litres/acre, per-day trace, and the assumption list.
- [x] 4. Create `backend/tests/test_irrigation.py` — table-driven: rain suppresses a scheduled irrigation, a dry spell triggers one, a later stage raises the amount, depletion never goes negative, mm-to-litre maths holds, spray waits on rain and on high wind. Run `.venv/bin/pytest -q` and get a green, non-zero test count.
- [x] 5. Create `backend/app/services/narration.py` — pure Hindi and English templates that render the engine's numbers into the sentence a farmer reads and hears. Separate functions per action so `WAIT_RAIN` cannot mis-word an irrigate-today decision. Unit-test the templates for both crops and both actions.
- [x] 6. Extend `backend/app/models/schemas.py` with `AdviceRequest` / `AdviceResponse` and add `POST /api/advice` to `backend/app/main.py` wiring request -> openmeteo.get_forecast -> irrigation.advise -> narration. 422 on a future sowing date or an unknown crop, 502 on upstream failure (never an empty result). Verify with a TestClient call against the real forecast.
- [x] 7. Scaffold the frontend: add react, react-dom, vite and @vitejs/plugin-react to `frontend/package.json`, create `frontend/vite.config.js` with the `/api` proxy to :8000 (this is the config the README claims exists and does not), run `npm install`, then confirm `npm run build` passes and the proxy actually reaches the backend.
- [x] 8. Create `frontend/src/lib/api.js` (fetch with timeout and distinguishable error kinds), `frontend/src/lib/speech.js` (hi-IN and en-IN via speechSynthesis, feature-detected, cancels on language toggle, silent when unsupported), and `frontend/src/lib/offline.js` (localStorage save/load of the last advice with its timestamp).
- [x] 9. Build the single screen: `frontend/src/App.jsx` holding village -> crop -> sowing date -> result, with `src/components/VillagePicker.jsx` (debounced search over /api/locations/search) and `src/components/AdviceCard.jsx` (the action, mm and litres, the Hindi/English line, source and assumption chips, spray and urea rows, weather strip). Add `frontend/src/styles/app.css` styled mobile-first from the tokens only, 44px touch targets, no colour literals.
- [ ] 10. Browser pass at a 390px viewport: search a real village, pick wheat and a past sowing date, get a real advice, play the Hindi voice, toggle to English, then kill the backend and confirm the cached advice still renders with its timestamp. Fix what actually breaks.
- [~] 11. Docs done: `plan.md` and `COVEXCODE.md` updated with verified commands and the confirmed upstream field names. **Contrast re-check and Google-Fonts payload trimming deliberately skipped by decision** — not verified, so the rest of this step is not ticked.

## Not doing

- A service worker / full PWA install — real offline app shell needs caching strategies and versioning; the brief says last advice cached, which localStorage does, and I will not claim more than that in the UI.
- LLM narration polish — the deterministic templates already satisfy 'no network in critical path'; adding a provider means a key, a failure mode and a data cost for no demo gain.
- Tailwind — described in the README, absent from the project, and redundant against the existing token stylesheet.
- Crops beyond wheat and rice, multi-screen navigation, auth, fields/plots, and an advice history — all explicitly outside 'one screen, one result'.
- Fabricated ICAR/SAU citations to fill every `source` slot — rules cite FAO-56 where that is the true origin, or are labelled as operational thresholds in the UI.

