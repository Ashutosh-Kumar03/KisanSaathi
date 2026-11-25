import { useMemo, useRef, useState } from 'react'
import AdviceCard from './components/AdviceCard.jsx'
import VillagePicker from './components/VillagePicker.jsx'
import { ApiError, fetchAdvice } from './lib/api.js'
import { loadLastAdvice, saveLastAdvice } from './lib/offline.js'
import { stopSpeaking } from './lib/speech.js'

/**
 * One screen, one result.
 *
 * Deliberately a single page: village, crop, sowing date, then the advice. No
 * navigation, no history, no second screen to get lost on. A farmer opens this
 * standing in a field with one question, so the shortest path from opening it
 * to reading the answer is the whole design.
 *
 * The advice is fetched from our backend, which computes it deterministically
 * from the real Open-Meteo forecast. Nothing here invents a number: if the
 * request fails the screen says so, and offers the last real advice it saw
 * rather than a plausible-looking guess.
 */

const CROPS = [
  { key: 'wheat', labelHi: 'गेहूँ', labelEn: 'Wheat' },
  { key: 'rice', labelHi: 'धान', labelEn: 'Rice' },
]

const SOILS = [
  { key: 'sandy', labelHi: 'रेतीली', labelEn: 'Sandy' },
  { key: 'loam', labelHi: 'दोमट', labelEn: 'Loam' },
  { key: 'clay', labelHi: 'चिकनी', labelEn: 'Clay' },
]

function todayISO() {
  const now = new Date()
  // Local date, not UTC: a farmer sowing "today" means their today.
  const offset = now.getTimezoneOffset() * 60000
  return new Date(now.getTime() - offset).toISOString().slice(0, 10)
}

export default function App() {
  const [location, setLocation] = useState(null)
  const [crop, setCrop] = useState('wheat')
  const [sowingDate, setSowingDate] = useState(() => {
    const d = new Date()
    d.setDate(d.getDate() - 35)
    const offset = d.getTimezoneOffset() * 60000
    return new Date(d.getTime() - offset).toISOString().slice(0, 10)
  })

  const [advice, setAdvice] = useState(null)
  const [source, setSource] = useState(null) // 'live' | { cachedAt }
  const [cachedAdvice, setCachedAdvice] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [language, setLanguage] = useState('hi')
  const [lastIrrigation, setLastIrrigation] = useState('')
  const [lastIrrigationMm, setLastIrrigationMm] = useState('')
  const [usualDays, setUsualDays] = useState('')
  const [soil, setSoil] = useState('')

  const resultRef = useRef(null)
  const maxDate = useMemo(todayISO, [])

  async function handleSubmit(event) {
    event.preventDefault()
    if (!location || loading) return

    stopSpeaking()
    setLoading(true)
    setError(null)

    try {
      const fresh = await fetchAdvice({
        crop,
        sowingDate,
        location,
        soil: soil || null,
        lastIrrigationDate: lastIrrigation || null,
        lastIrrigationMm: lastIrrigationMm === '' ? null : Number(lastIrrigationMm),
        usualIntervalDays: usualDays === '' ? null : Number(usualDays),
      })
      setAdvice(fresh)
      setSource('live')
      saveLastAdvice(fresh)
      // Move focus to the answer so a screen reader lands on the decision,
      // not on the form it just left.
      requestAnimationFrame(() => resultRef.current?.focus())
    } catch (err) {
      const kind = err instanceof ApiError ? err.kind : 'unknown'
      let message = 'कुछ गड़बड़ हो गई।'
      if (kind === 'offline') message = 'इंटरनेट या सर्वर से संपर्क नहीं हो पाया।'
      else if (kind === 'upstream') message = 'मौसम सेवा अभी जवाब नहीं दे रही है। थोड़ी देर बाद फिर कोशिश करें।'
      else if (kind === 'invalid') message = 'दर्ज की गई जानकारी ठीक नहीं है।'
      setError({ message, detail: err?.detail })
      setAdvice(null)

      // Fall back to the last real advice, clearly marked as old. Read it here
      // rather than at mount time, so it is the most recent one that failed
      // over, not whatever was cached when the tab opened.
      const cached = loadLastAdvice()
      if (cached) {
        setCachedAdvice(cached)
        setSource({ cachedAt: cached.savedAt })
      } else {
        setSource(null)
      }
    } finally {
      setLoading(false)
    }
  }

  const showingCached = typeof source === 'object' && source !== null
  const displayAdvice = showingCached ? cachedAdvice?.advice : advice

  return (
    <div className="shell">
      <main className="wrap">
        <header className="masthead">
          <h1>किसान साथी</h1>
          <p>आज पानी दें या रुकें — मौसम के हिसाब से सलाह</p>
        </header>

        <form className="form" onSubmit={handleSubmit}>
          <VillagePicker value={location} onChange={setLocation} />

          <div className="field">
            <span className="field-label" id="crop-label">
              फसल
            </span>
            <div className="choices" role="group" aria-labelledby="crop-label">
              {CROPS.map((option) => (
                <button
                  key={option.key}
                  type="button"
                  className="choice"
                  aria-pressed={crop === option.key}
                  onClick={() => setCrop(option.key)}
                >
                  {option.labelHi}
                </button>
              ))}
            </div>
          </div>

          <div className="field">
            <label className="field-label" htmlFor="sowing">
              बोने की तारीख
            </label>
            <input
              id="sowing"
              className="input touch"
              type="date"
              value={sowingDate}
              max={maxDate}
              onChange={(event) => setSowingDate(event.target.value)}
              required
            />
          </div>

          <div className="field">
            <span className="field-label" id="soil-label">
              मिट्टी का प्रकार
            </span>
            <div className="choices" role="group" aria-labelledby="soil-label">
              {SOILS.map((option) => (
                <button
                  key={option.key}
                  type="button"
                  className="choice"
                  aria-pressed={soil === option.key}
                  onClick={() => setSoil(soil === option.key ? '' : option.key)}
                >
                  {option.labelHi}
                </button>
              ))}
            </div>
            <p className="notes" style={{ margin: 'var(--space-1) 0 0' }}>
              {soil
                ? 'आपकी मिट्टी के हिसाब से पानी की मात्रा तय होगी।'
                : 'न चुनें तो दोमट माना जाएगा और सलाह में यह लिखा रहेगा।'}
            </p>
          </div>

          <div className="field">
            <label className="field-label" htmlFor="last-irrigation">
              पिछली सिंचाई की तारीख
              <span className="notes" style={{ marginLeft: 'var(--space-1)' }}>
                (वैकल्पिक)
              </span>
            </label>
            <input
              id="last-irrigation"
              className="input touch"
              type="date"
              value={lastIrrigation}
              min={sowingDate}
              max={maxDate}
              onChange={(event) => setLastIrrigation(event.target.value)}
            />
            <p className="notes" style={{ margin: 'var(--space-1) 0 0' }}>
              {lastIrrigation
                ? 'उस दिन मिट्टी में पानी पूरा मानकर गणना होगी।'
                : 'खाली छोड़ें तो सलाह मानेगी कि बोने के बाद से सिंचाई नहीं हुई।'}
            </p>

            <label className="field-label" htmlFor="last-irrigation-mm" style={{ marginTop: 'var(--space-2)' }}>
              उस सिंचाई में कितना पानी दिया (मिमी)
              <span className="notes" style={{ marginLeft: 'var(--space-1)' }}>
                (वैकल्पिक)
              </span>
            </label>
            <input
              id="last-irrigation-mm"
              className="input touch"
              type="number"
              inputMode="decimal"
              min="0"
              step="1"
              placeholder="जैसे: 50"
              value={lastIrrigationMm}
              onChange={(event) => setLastIrrigationMm(event.target.value)}
              disabled={!lastIrrigation}
            />
            <p className="notes" style={{ margin: 'var(--space-1) 0 0' }}>
              1 इंच = 25.4 मिमी। खाली छोड़ें तो माना जाएगा कि उस सिंचाई से मिट्टी पूरी भर गई।
            </p>
            {lastIrrigationMm !== '' && (
              <p className="notes" style={{ margin: 'var(--space-1) 0 0' }}>
                करीब {(Number(lastIrrigationMm) / 25.4).toFixed(1)} इंच
              </p>
            )}
          </div>

          <div className="field">
            <label className="field-label" htmlFor="usual-days">
              आमतौर पर कितने दिन में सिंचाई करते हैं
              <span className="notes" style={{ marginLeft: 'var(--space-1)' }}>
                (वैकल्पिक)
              </span>
            </label>
            <input
              id="usual-days"
              className="input touch"
              type="number"
              inputMode="numeric"
              min="1"
              step="1"
              placeholder="जैसे: 12"
              value={usualDays}
              onChange={(event) => setUsualDays(event.target.value)}
            />
            <p className="notes" style={{ margin: 'var(--space-1) 0 0' }}>
              सिर्फ़ तुलना के लिए — सलाह की गणना इससे नहीं बदलती।
            </p>
          </div>

          <button
            type="submit"
            className="btn btn-primary btn-block"
            disabled={!location || !sowingDate || loading}
          >
            {loading ? 'मौसम देख रहे हैं…' : 'सलाह देखें'}
          </button>
          {!location && (
            <p className="notes" style={{ margin: 0 }}>
              पहले अपना गाँव चुनें।
            </p>
          )}
        </form>

        {error && (
          <div className="results">
            <div className="card error" role="alert">
              <p>
                <strong>{error.message}</strong>
              </p>
              {showingCached && (
                <p className="notes" style={{ margin: 0 }}>
                  नीचे पिछली बार की सलाह दिखाई गई है, जो अब ताज़ा नहीं है।
                </p>
              )}
            </div>
          </div>
        )}

        {displayAdvice && (
          <div className="results" ref={resultRef} tabIndex={-1} aria-live="polite">
            {showingCached && (
              <div className="stale-banner">
                पुरानी सलाह — यह ताज़ा मौसम पर आधारित नहीं है। नई सलाह के लिए फिर कोशिश करें।
              </div>
            )}
            <AdviceCard
              advice={displayAdvice}
              language={language}
              onLanguageChange={setLanguage}
            />
          </div>
        )}
      </main>
    </div>
  )
}
