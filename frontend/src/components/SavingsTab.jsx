/**
 * The बचत (savings) tab.
 *
 * Shows one comparison: the farmer's own habit against what the model would
 * have advised, run over the same real weather. The weather is the part neither
 * of them controls, so holding it fixed is the only way the difference means
 * anything.
 *
 * Three rules this component obeys, because a savings figure is the easiest
 * number in this app to fake:
 *
 *   1. No habit, no number. `savings === null` renders a prompt asking for the
 *      inputs, never a placeholder or a zero.
 *   2. Rupees only from stated pump figures. When they are missing, the reason
 *      is printed in words rather than leaving a blank the farmer must guess at.
 *   3. Every assumption is listed, and the whole panel is labelled an estimate.
 *
 * It computes nothing itself. Millimetres, litres, hours and rupees all arrive
 * from the backend, so the arithmetic exists in exactly one place.
 */

import { useState } from 'react'

const LABEL_HI = 'अनुमान: आपकी अपनी आदत और मॉडल की सलाह की तुलना'
const LABEL_EN = "Estimate: comparing your own habit with the model's advice"

/** Lakh-grouped integer, matching the backend's Indian formatting. */
function inr(value) {
  const n = Math.round(Math.abs(value))
  const digits = String(n)
  if (digits.length <= 3) return (value < 0 ? '-' : '') + digits
  const head = digits.slice(0, -3)
  const tail = digits.slice(-3)
  let parts = []
  let rest = head
  while (rest.length > 2) {
    parts.unshift(rest.slice(-2))
    rest = rest.slice(0, -2)
  }
  if (rest) parts.unshift(rest)
  return (value < 0 ? '-' : '') + parts.join(',') + ',' + tail
}

export default function SavingsTab({ savings, language }) {
  if (!savings) {
    return (
      <section className="card">
        <h2 style={{ fontSize: 'var(--text-lg)' }}>बचत</h2>
        <p style={{ margin: 0 }}>
          {language === 'hi'
            ? 'बचत देखने के लिए बताइए: आप आमतौर पर कितने दिन में सिंचाई करते हैं और हर बार कितना पानी देते हैं। ये दोनों भरे बिना कोई बचत नहीं दिखाई जा सकती।'
            : 'To see your savings, tell us how often you usually irrigate and how much water you apply each time. Without both, no saving can be shown.'}
        </p>
        <p className="notes" style={{ margin: 'var(--space-2) 0 0' }}>
          {language === 'hi'
            ? 'फिर से सलाह लें — ऊपर "आमतौर पर कितने दिन में" और "हर बार कितना पानी" भरें।'
            : 'Ask for advice again with the habit fields filled in above.'}
        </p>
      </section>
    )
  }

  const positive = savings.saved_mm > 0
  const negative = savings.saved_mm < 0
  const money = savings.money_saved != null

  return (
    <>
      <section className="card">
        <p
          className="notes"
          style={{
            margin: '0 0 var(--space-2)',
            borderLeft: '2px solid var(--ochre)',
            paddingLeft: 'var(--space-2)',
          }}
        >
          {language === 'hi' ? LABEL_HI : LABEL_EN}
        </p>

        <h2 style={{ fontSize: 'var(--text-lg)' }}>बचत</h2>

        {positive && (
          <>
            <div className="mm-row">
              <span className="stat tabular-nums">{savings.saved_mm}</span>
              <span className="stat-unit">मिमी पानी</span>
            </div>
            <p style={{ margin: '0 0 var(--space-2)' }}>
              करीब{' '}
              <strong className="tabular-nums">
                {inr(savings.saved_litres_per_acre)}
              </strong>{' '}
              लीटर प्रति एकड़ बच सकता है
            </p>
          </>
        )}

        {!positive && !negative && (
          <p style={{ margin: '0 0 var(--space-2)' }}>
            {language === 'hi'
              ? 'लगभग बराबर पानी लगता है — कोई ख़ास बचत नहीं।'
              : 'About the same amount of water — no meaningful saving.'}
          </p>
        )}

        {negative && (
          <p style={{ margin: '0 0 var(--space-2)' }}>
            {language === 'hi'
              ? `आपकी आदत में ${Math.abs(savings.saved_mm)} मिमी पानी कम लगता है — यानी आप पहले से कम पानी दे रहे हैं।`
              : `Your habit uses ${Math.abs(savings.saved_mm)} mm less — you are already applying less water than advised.`}
          </p>
        )}

        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 'var(--text-sm)' }}>
          <thead>
            <tr>
              <th style={{ textAlign: 'left', padding: 'var(--space-1) 0' }}>
                {language === 'hi' ? 'तरीका' : 'Schedule'}
              </th>
              <th style={{ textAlign: 'right', padding: 'var(--space-1) 0' }}>
                {language === 'hi' ? 'पानी' : 'Water'}
              </th>
              <th style={{ textAlign: 'right', padding: 'var(--space-1) 0' }}>
                {language === 'hi' ? 'बार' : 'Times'}
              </th>
            </tr>
          </thead>
          <tbody>
            <tr style={{ borderTop: '1px solid var(--border)' }}>
              <td style={{ padding: 'var(--space-1) 0' }}>
                {language === 'hi'
                  ? `आपकी आदत (हर ${savings.habit_interval_days} दिन)`
                  : `Your habit (every ${savings.habit_interval_days} days)`}
              </td>
              <td className="tabular-nums" style={{ textAlign: 'right' }}>
                {savings.habit_total_mm} मिमी
              </td>
              <td className="tabular-nums" style={{ textAlign: 'right' }}>
                {savings.habit_irrigations}
              </td>
            </tr>
            <tr style={{ borderTop: '1px solid var(--border)' }}>
              <td style={{ padding: 'var(--space-1) 0' }}>
                {language === 'hi' ? 'सलाह' : 'Advised'}
              </td>
              <td className="tabular-nums" style={{ textAlign: 'right' }}>
                {savings.advised_total_mm} मिमी
              </td>
              <td className="tabular-nums" style={{ textAlign: 'right' }}>
                {savings.advised_irrigations}
              </td>
            </tr>
          </tbody>
        </table>
      </section>

      <section className="card">
        <h3 style={{ fontSize: 'var(--text-base)' }}>
          {language === 'hi' ? 'पंप और रुपये' : 'Pump and rupees'}
        </h3>
        {money ? (
          <>
            <p style={{ margin: '0 0 var(--space-1)' }}>
              {language === 'hi' ? 'पंप करीब' : 'The pump runs about'}{' '}
              <strong className="tabular-nums">{savings.pump_hours_saved}</strong>{' '}
              {language === 'hi' ? 'घंटे कम चलेगा' : 'hours less'}
            </p>
            <p style={{ margin: 0 }}>
              {language === 'hi' ? 'करीब' : 'About'} <strong>₹{inr(savings.money_saved)}</strong>{' '}
              {language === 'hi' ? 'की बचत' : 'saved'}
            </p>
          </>
        ) : (
          <p className="notes" style={{ margin: 0 }}>
            {savings.money_unavailable_reason === 'both'
              ? language === 'hi'
                ? '₹ की बचत दिखाने के लिए पंप की क्षमता (लीटर/घंटा) और प्रति घंटे की लागत, दोनों भरें।'
                : 'To show savings in rupees, fill in both the pump discharge (litres/hour) and the cost per hour.'
              : language === 'hi'
                ? 'पंप और बिजली-डीज़ल की जानकारी नहीं दी गई, इसलिए बचत सिर्फ़ पानी में दिखाई गई है — रुपये में नहीं।'
                : 'No pump or fuel details were given, so the saving is shown in water only, not in rupees.'}
          </p>
        )}
      </section>

      <section className="card notes">
        <h3 style={{ fontSize: 'var(--text-sm)', marginBottom: 'var(--space-2)' }}>
          {language === 'hi' ? 'यह अनुमान किन बातों पर टिका है' : 'What this estimate rests on'}
        </h3>
        <ul>
          {savings.assumptions.map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
        <p style={{ margin: 'var(--space-2) 0 0', fontSize: 'var(--text-xs)' }}>
          {language === 'hi'
            ? 'यह बचत अनुमान है, गारंटी नहीं — मौसम बदले तो हिसाब भी बदलेगा।'
            : 'This is an estimate, not a guarantee — if the weather changes, so does the arithmetic.'}
        </p>
      </section>
    </>
  )
}
