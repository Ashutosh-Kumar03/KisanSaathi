# किसान साथी — KisanSaathi

Hindi-first irrigation advisory for small and marginal farmers in India.

Pick your village, your crop (wheat or rice) and the day you sowed. The app fetches the real
forecast and tells you one thing: **irrigate today, or wait** — with the water amount in millimetres
and litres per acre, in Hindi, spoken aloud, plus whether you should hold off spraying or applying
urea because rain is coming.

Built for HACKNOVA 2026, track: Agriculture and Rural Livelihoods (Track 3, problem 2 — better
decisions about weather, irrigation and agricultural inputs).

## The problem

A farmer deciding whether to irrigate today is making a bet with real money and a real crop on the
table. Irrigate too early and the water is wasted; too late, and yield is lost. The stages where a
shortage hurts most are named and cited in the crop data — for wheat, TNAU identifies crown root
initiation and flowering as the two most critical. The information needed to make that bet well
exists: a free public weather forecast already says how much rain is coming. What is missing is the
step from *"6 mm of rain on Thursday"* to *"do not run the pump today."*

That step is a calculation, not a conversation. It is a soil water balance: how much water the crop
has used since sowing, how much is still stored, and whether the deficit has reached the point where
the plant starts to suffer. The app does that arithmetic and says the answer in one sentence.

**The rule that shapes the whole design:** the recommendation is computed by deterministic code,
never by a language model. `services/irrigation.py` is a pure function with no I/O at all, so it
cannot reach a network or a model even by accident. Narration is a separate module that formats
numbers it is handed and has no way to compute one. Hallucinated agronomic advice is real harm —
this app is built so that failure is structurally impossible rather than merely unlikely.

## Who it helps

- **A wheat or rice farmer deciding today whether to run a pump.** Gets a yes/no and a number, not
  a dashboard to interpret.
- **A farmer who reads Hindi but not English.** Hindi is the primary text, not a translation, and the
  advice can be read aloud so it works for someone who does not read comfortably at all.
- **A farmer on a cheap phone with a metered connection.** The whole app is 51 kB gzipped of
  JavaScript, with no images, no audio files and no icon library. The voice is the phone's own speech
  synthesis, so listening costs no data.

## How it works

```
village + crop + sowing date
        |
        v
Open-Meteo (no API key)  ->  observed days since sowing + 8-day forecast
        |
        v
services/irrigation.py   ->  FAO-56 water balance (pure, no I/O)
        |
        v
services/narration.py    ->  Hindi + English sentences (no LLM)
        |
        v
the single screen        ->  decision, mm, litres/acre, spray + urea, forecast, sources
```

The balance, per FAO-56 single crop coefficient:

```
ETc(i) = Kc(i) x ET0(i)
Dr(i)  = Dr(i-1) - effective_rain(i) + ETc(i)      clamped to [0, TAW]
TAW    = 150 mm/m x root_depth
RAW    = p x TAW                                   irrigate when Dr >= RAW
gross  = net / application_efficiency              litres = mm x 4046.86 per acre
```

Two details that turn out to matter:

- **Real history, not a fresh start.** The engine is given the observed days since sowing. Starting
  the balance at field capacity *today* means a single day of demand can never reach the stress
  point, so the app could never justify irrigating — it would confidently always say wait.
- **Today, not the end of the week.** The decision reads depletion at the end of *today*. Reading it
  at the end of the forecast let dry days later in the week pull today's advice forward.

## Where the numbers come from

Every agronomic value lives in one file, `backend/app/data/crop_rules.py`, and each value carries its
own `source` string — so the citation is data, not a comment that can drift away from the number.

| What | Source |
|---|---|
| Stage lengths | FAO-56 (Allen et al. 1998), Table 11 |
| Kc, initial / mid / end | FAO-56, Table 12 |
| Root depth, depletion fraction p | FAO-56, Table 22 |
| Wheat critical irrigation windows | TNAU Agritech Portal, Crop Production — Wheat |
| Rice critical window | FAO-56, Table 11 stage boundaries |
| Soil (loam, 150 mm/m), application efficiency 70%, spray and urea thresholds | `OPERATIONAL` |

The last row is the honest one: those thresholds are this app's own judgement calls, they have no
published source, and the UI shows them to the farmer as assumptions rather than dressing them in a
citation. No ICAR or state-university reference appears that could not be read at source — a citation
nobody can check borrows authority the rule may not have. Two tests fail the build if a citation
outside the allowed set ever appears.

## Run it

Two processes, two terminals.

**Backend** (port 8000):

```sh
cd backend
.venv/bin/uvicorn app.main:app --reload
```

The venv is already built. If it is missing:

```sh
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn app.main:app --reload
```

**Frontend** (port 5173):

```sh
cd frontend
npm install
npm run dev
```

Then open **http://localhost:5173**.

> Note: Vite binds to `localhost` (IPv6) here, so `127.0.0.1:5173` will refuse even when the dev
> server is perfectly healthy. Use `localhost`.

No API key or environment variable is needed. Open-Meteo requires none, and every setting has a
working default — the app starts with zero configuration.

**Tests:**

```sh
cd backend
.venv/bin/pytest -q      # 56 passed
```

**Production build:**

```sh
cd frontend
npm run build            # 157 kB js / 51 kB gzipped
```

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/health` | Liveness plus which optional integrations are configured |
| `GET` | `/api/locations/search?q=` | Indian locations by name (restricted to `countryCode=IN`) |
| `GET` | `/api/weather?lat=&lon=` | Daily ET0, rain, temperature, wind for a point |
| `POST` | `/api/advice` | The decision: crop + sowing date + coordinates |

Upstream failure returns `502`, never an empty result — the screen must be able to say "the weather
service is down" and never confuse it with "no need to irrigate". Bad input returns `422`.

## How Covexcode was used

This project was built in a single Covexcode session. The git log is the record:

```
adf72c0  Scaffold backend and frontend structure
26fe672  step 2: sourced crop rule data file (FAO-56 T11/T12/T22, TNAU wheat stages)
190f905  step 3: pure FAO-56 water-balance engine
8f5211d  step 4: table-driven tests for the engine and the crop data
7855486  step 5: deterministic Hindi and English narration
2bb17e0  step 6: POST /api/advice wiring weather through the engine to narration
148bb5b  step 7: real frontend build with a working /api proxy
8471aa5  step 8: frontend libs for api, speech and offline cache
2769e94  step 9: the single screen — village, crop, sowing date, one result
```

What the agent actually did, and what it deliberately did not:

- **Verified before building.** Step 1 was a live request to Open-Meteo to confirm the exact daily
  field names (`wind_speed_10m_max`, `wind_gusts_10m_max`) rather than guessing them, and a fetch of
  the FAO-56 tables themselves to read the Kc, root-depth and depletion values at source.
- **Refused to invent citations.** Asked for ICAR and state-university sources on every rule, it read
  the wheat critical-stage timing from TNAU directly, could not reach an equivalent rice page, and
  cited FAO-56 alone for rice instead of filling the gap with something plausible. Thresholds with no
  published source were labelled `OPERATIONAL` and surfaced in the UI as assumptions.
- **Found two real bugs by testing, not by reading.** The decision was reading depletion at the end of
  the forecast week instead of the end of today; and `get_forecast` had no `past_days`, so the balance
  started at field capacity and could essentially never justify irrigating. Both are recorded in the
  commit messages.
- **Respected the architectural rule while implementing it.** The engine was written with no I/O and
  the card was written to compute nothing — not even a percentage — so the "no model decides" claim
  is enforced by the module boundaries rather than by comment.
- **Owned what it could not verify.** When it hit a mid-session tooling failure it said so and stopped
  rather than looping; after building the frontend it reported that browser checks were unavailable in
  that client, rather than claiming it had seen the page render. The 390px visual pass and the
  on-device speech test remain unchecked in `plan.md` for that reason.

Tooling: FastAPI + Pydantic backend, React + Vite frontend, plain CSS reading one token file. Python
3.15.2, Node v24.12.0.

## Value

- **One decision, not a dashboard.** The output is a sentence a farmer can act on, with the arithmetic
  behind it available but not in the way.
- **Deterministic and auditable.** The same weather and the same sowing date always produce the same
  advice. Every number traces to a table and a row, and the two guard tests keep it that way.
- **No key, no cost, no account.** Open-Meteo needs no API key and there is no LLM in the request
  path, so the app runs offline from any paid service and cannot bill per farmer.
- **Works on the phone people actually have.** 51 kB gzipped, no images, no audio downloads, voice via
  the built-in speech synthesis. Hindi first, read aloud.
- **Degrades honestly.** No weather → `502` and an explanation, never invented advice. Last advice
  cached in `localStorage` and re-shown with a visible "this is not fresh" banner. No Hindi voice on
  the device → the button is replaced by a plain note and the text stays.
- **The agronomy is testable without a network.** 56 tests, no fixtures beyond plain dates, because
  the engine is a pure function.

## Known limits

- The offline cache is one result in `localStorage`, not a service worker. The app shell still needs a
  network to load; offline means "your last advice is still readable", not "the app works offline".
- Soil is assumed to be loam at 150 mm/m available water, and irrigation is assumed to be flood or
  surface application at 70% efficiency. Both are shown to the farmer as assumptions.
- Depletion is modelled from receipt of weather data, not measured. Real soil moisture would be
  better; this is the honest version of what a forecast can support.
- Only wheat and rice, one screen, no accounts, no history. Deliberate — see `plan.md`.
- Browser verification at 390px and speech on a real device are still outstanding.

## Layout

```
backend/
  app/
    main.py              FastAPI routes
    config.py            settings, every one with a working default
    data/crop_rules.py   THE crop data file, every value with its source
    services/
      irrigation.py      pure FAO-56 water balance (no I/O)
      narration.py       Hindi + English templates (no LLM)
      openmeteo.py       geocoding + forecast, cache, Hargreaves ET0 fallback
    models/schemas.py    Pydantic contracts — the JSON the UI consumes
  tests/                 56 tests: irrigation, narration, api
frontend/
  vite.config.js         /api and /health proxy to the backend
  src/
    App.jsx              the single screen
    components/          VillagePicker, AdviceCard
    lib/                 api.js, speech.js, offline.js
    styles/app.css       mobile-first, tokens only
  public/design-tokens.css
```
