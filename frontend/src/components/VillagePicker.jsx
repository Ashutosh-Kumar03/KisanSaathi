import { useEffect, useRef, useState } from 'react'
import { ApiError, searchLocations } from '../lib/api.js'

/**
 * Village search, backed by the real India-restricted geocoding endpoint.
 *
 * The search is debounced because every keystroke would otherwise be a request
 * on a metered connection, which is exactly the cost this app is trying not to
 * impose. Two characters minimum, because one letter matches half of India.
 *
 * A previously-chosen village stays chosen while the user types a new search:
 * losing a selection because a stray tap landed in the box would be a small
 * cruelty that costs a farmer the whole flow.
 */
export default function VillagePicker({ value, onChange }) {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState([])
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const boxRef = useRef(null)

  useEffect(() => {
    if (query.trim().length < 2) {
      setResults([])
      setBusy(false)
      setError(null)
      return
    }

    let cancelled = false
    setBusy(true)
    const timer = setTimeout(async () => {
      try {
        const found = await searchLocations(query.trim())
        if (cancelled) return
        setResults(found)
        setOpen(true)
        setError(null)
      } catch (err) {
        if (cancelled) return
        setResults([])
        setError(
          err instanceof ApiError && err.kind === 'offline'
            ? 'गाँव खोजने के लिए इंटरनेट चाहिए।'
            : 'गाँव नहीं मिल पाए। नाम फिर से लिखें।',
        )
      } finally {
        if (!cancelled) setBusy(false)
      }
    }, 350)

    return () => {
      cancelled = true
      clearTimeout(timer)
    }
  }, [query])

  function choose(place) {
    onChange(place)
    setQuery('')
    setResults([])
    setOpen(false)
    // Return focus to the input so the keyboard flow continues naturally.
    boxRef.current?.focus()
  }

  return (
    <div className="field">
      <label className="field-label" htmlFor="village">
        गाँव या ज़िला
      </label>
      <input
        id="village"
        ref={boxRef}
        className="input touch"
        type="text"
        inputMode="search"
        autoComplete="off"
        placeholder="जैसे: पटना"
        value={query}
        onChange={(event) => setQuery(event.target.value)}
        onFocus={() => results.length && setOpen(true)}
        aria-describedby="village-help"
      />

      <p className="notes" id="village-help" style={{ margin: 'var(--space-1) 0 0' }}>
        {value
          ? `चुना गया: ${value.display_name}`
          : busy
            ? 'खोज रहे हैं…'
            : 'गाँव का नाम लिखना शुरू करें'}
      </p>

      {error && (
        <p className="notes" role="status" style={{ color: 'var(--text-muted)' }}>
          {error}
        </p>
      )}

      {open && results.length > 0 && (
        <ul className="suggestions">
          {results.map((place) => (
            <li key={place.id}>
              <button type="button" onClick={() => choose(place)}>
                {place.display_name}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
