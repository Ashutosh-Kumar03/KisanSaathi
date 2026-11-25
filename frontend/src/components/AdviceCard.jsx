import { useEffect, useState } from 'react'
import { hasVoiceFor, speak, speechSupported, stopSpeaking } from '../lib/speech.js'

/**
 * The result: the decision, the number, and the reasons behind it.
 *
 * Order on the card is the order a farmer needs it: what to do, how much, why,
 * then the two "should this wait" questions about spraying and fertiliser, then
 * the weather that drove it. The citations and assumptions sit last, because
 * they matter for trust but must not push the decision off the first screen.
 *
 * Nothing on this card is computed here. Every figure comes from the backend,
 * which is the point: if this file were ever to derive a number itself, the
 * guarantee that the language model never decides would quietly stop meaning
 * anything.
 */

const ACTION_STYLE = {
  IRRIGATE_TODAY: { badge: 'badge-action', tone: 'irrigate' },
  WAIT_RAIN: { badge: 'badge-hold', tone: 'hold' },
  SOIL_MOISTURE_OK: { badge: 'badge-hold', tone: 'hold' },
  SEASON_OVER: { badge: 'badge-hold', tone: 'hold' },
}

/** Render an ISO date the way it reads in Hindi: 12-11-2026. */
function formatDate(iso) {
  if (!iso) return ''
  const [year, month, day] = iso.split('-')
  return `${day}-${month}-${year}`
}

function VerdictBadge({ verdict, language }) {  const map = {
    go: { cls: 'badge badge-action', hi: 'अभी करें', en: 'Go ahead' },
    wait: { cls: 'badge badge-hold', hi: 'रुकें', en: 'Wait' },
    unknown: { cls: 'badge badge-hold', hi: 'पता नहीं', en: 'Not known' },
  }
  const entry = map[verdict] || map.unknown
  return <span className={entry.cls}>{language === 'hi' ? entry.hi : entry.en}</span>
}

export default function AdviceCard({ advice, language, onLanguageChange }) {
  const [speakState, setSpeakState] = useState('idle') // idle | speaking | unsupported

  const style = ACTION_STYLE[advice.action] || ACTION_STYLE.SOIL_MOISTURE_OK
  const isIrrigate = advice.action === 'IRRIGATE_TODAY'
  const text = language === 'hi' ? advice.hindi : advice.english
  const headline = language === 'hi' ? advice.headline_hi : advice.headline_en

  // Stop any speech when the card unmounts or the language flips, so a Hindi
  // sentence never keeps playing over an English one.
  useEffect(() => () => stopSpeaking(), [])
  useEffect(() => {
    stopSpeaking()
    setSpeakState('idle')
  }, [language, advice.action])

  const canSpeak = speechSupported() && hasVoiceFor(language)

  function handleSpeak() {
    if (speakState === 'speaking') {
      stopSpeaking()
      setSpeakState('idle')
      return
    }
    const ok = speak(text, language)
    setSpeakState(ok ? 'speaking' : 'unsupported')
  }

  return (
    <>
      <section className="card" aria-labelledby="advice-headline">
        <div className="headline">
          <h2 id="advice-headline">{headline}</h2>
          <span className={`badge ${style.badge}`}>
            {advice.age_days} दिन
          </span>
        </div>

        {isIrrigate && (
          <div className="mm-row">
            <span className="stat tabular-nums">{advice.gross_mm}</span>
            <span className="stat-unit">मिमी पानी</span>
          </div>
        )}

        {isIrrigate && (
          <p style={{ margin: '0 0 var(--space-2)' }}>
            यानी करीब{' '}
            <strong className="tabular-nums">
              {advice.litres_per_acre.toLocaleString('en-IN')}
            </strong>{' '}
            लीटर प्रति एकड़
          </p>
        )}

        <p className="hindi-text" style={{ margin: 'var(--space-3) 0 var(--space-3)' }}>
          {text}
        </p>

        {/* The soil-moisture assumption is stated here as well as in the
            details below, because it changes the answer: "assumed no
            irrigation" is a different claim from "assumed you watered on the
            12th", and only the farmer knows which is true. */}
        <p className="notes" style={{ margin: '0 0 var(--space-3)' }}>
          {advice.last_irrigation_date
            ? language === 'hi'
              ? `गणना में माना गया: पिछली सिंचाई ${formatDate(advice.last_irrigation_date)} को हुई थी।`
              : `Calculated assuming you last irrigated on ${formatDate(advice.last_irrigation_date)}.`
            : language === 'hi'
              ? 'यह सलाह मानती है कि बोने के बाद से सिंचाई नहीं हुई।'
              : 'This advice assumes no irrigation since sowing.'}
        </p>

        <div className="voice-row">
          {canSpeak ? (
            <button
              type="button"
              className="btn btn-secondary touch"
              onClick={handleSpeak}
              aria-label={speakState === 'speaking' ? 'पढ़ना रोकें' : 'सलाह सुनें'}
            >
              {speakState === 'speaking' ? '⏹ रोकें' : '🔊 सुनें'}
            </button>
          ) : (
            <span className="notes">
              इस फ़ोन में आवाज़ उपलब्ध नहीं है — सलाह पढ़ी जा सकती है।
            </span>
          )}

          <button
            type="button"
            className="btn btn-secondary touch"
            onClick={() => onLanguageChange(language === 'hi' ? 'en' : 'hi')}
          >
            {language === 'hi' ? 'English' : 'हिन्दी'}
          </button>
        </div>

        {advice.in_critical_window && advice.critical_window_label && (
          <p className="notes" style={{ marginTop: 'var(--space-3)' }}>
            ⚠ यह {advice.critical_window_label} का समय है — पानी की कमी से उपज पर असर पड़ता है।
          </p>
        )}
      </section>

      <section className="card" aria-labelledby="inputs-heading">
        <h3 id="inputs-heading" style={{ fontSize: 'var(--text-base)' }}>
          छिड़काव और खाद
        </h3>
        <div className="window-row">
          <VerdictBadge verdict={advice.spray.verdict} language={language} />
          <div className="window-body">
            <strong>छिड़काव</strong>
            <p>{language === 'hi' ? advice.spray.reason_hi : advice.spray.reason_en}</p>
          </div>
        </div>
        <div className="window-row">
          <VerdictBadge verdict={advice.urea.verdict} language={language} />
          <div className="window-body">
            <strong>यूरिया / खाद</strong>
            <p>{language === 'hi' ? advice.urea.reason_hi : advice.urea.reason_en}</p>
          </div>
        </div>
      </section>

      {advice.forecast?.length > 0 && (
        <section className="card" aria-labelledby="forecast-heading">
          <h3 id="forecast-heading" style={{ fontSize: 'var(--text-base)' }}>
            आगे का मौसम
          </h3>
          <div className="strip">
            {advice.forecast.slice(0, 7).map((day) => {
              const d = new Date(day.date + 'T00:00:00')
              const label = d.toLocaleDateString('hi-IN', {
                weekday: 'short',
                day: 'numeric',
              })
              return (
                <div className="strip-day" key={day.date}>
                  <span className="d">{label}</span>
                  <span className="v">{Math.round(day.rain_mm)} मिमी</span>
                  <span className="r">
                    {day.rain_probability_pct != null
                      ? `${day.rain_probability_pct}%`
                      : '—'}
                  </span>
                </div>
              )
            })}
          </div>
          <p className="notes" style={{ margin: 0 }}>
            बारिश का अनुमान (मिमी) और संभावना
          </p>
        </section>
      )}

      <section className="card notes" aria-labelledby="why-heading">
        <h3 id="why-heading" style={{ fontSize: 'var(--text-sm)', marginBottom: 'var(--space-2)' }}>
          यह सलाह किस आधार पर
        </h3>
        <p style={{ margin: '0 0 var(--space-1)', fontSize: 'var(--text-xs)' }}>
          मिट्टी:{' '}
          <strong>
            {language === 'hi' ? advice.soil_name_hi : advice.soil_name_en}
          </strong>{' '}
          · उपलब्ध पानी{' '}
          <strong className="tabular-nums">{advice.soil_available_water_mm_per_m} मिमी/मीटर</strong>
          {advice.soil_is_default && (
            <span> · मिट्टी नहीं चुनी, दोमट मानी गई</span>
          )}
        </p>
        <p style={{ margin: '0 0 var(--space-1)', fontSize: 'var(--text-xs)' }}>
          मिट्टी की नमी की कमी: <strong className="tabular-nums">{advice.depletion_mm} मिमी</strong>{' '}
          / सिंचाई की सीमा{' '}
          <strong className="tabular-nums">{advice.raw_mm} मिमी</strong> · कुल उपलब्ध पानी{' '}
          <strong className="tabular-nums">{advice.taw_mm} मिमी</strong>
        </p>
        <ul>
          {advice.assumptions.map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
        <p style={{ margin: 'var(--space-2) 0 var(--space-1)', fontSize: 'var(--text-xs)' }}>
          स्रोत:
        </p>
        <ul>
          {advice.sources.map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
        <p style={{ margin: 'var(--space-2) 0 0', fontSize: 'var(--text-xs)' }}>
          {advice.location_name} · {advice.crop_name_hi} ·{' '}
          {new Date(advice.generated_at).toLocaleString('hi-IN')}
        </p>
      </section>
    </>
  )
}
