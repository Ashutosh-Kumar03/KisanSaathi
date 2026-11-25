/**
 * The last advice, kept on the phone so a dead connection is not a dead end.
 *
 * A farmer who walked to the field, opened the app and found nothing because
 * the signal dropped has been failed by the design, not by the weather. So the
 * last real advice is stored and shown again with its timestamp and a visible
 * "this is not fresh" banner. It is never presented as current.
 *
 * What this deliberately is not: a service worker. The app shell itself still
 * needs a network to load, and pretending otherwise in the UI would be a lie.
 * This caches one result, which is what the brief asked for.
 */

const KEY = 'kisansaathi:last-advice:v1'

/**
 * Save an advice with the moment it was fetched. Wrapped in try/catch because
 * storage throws in private mode and when the quota is full, and losing the
 * cache must never break the screen the farmer is already reading.
 */
export function saveLastAdvice(advice) {
  try {
    const payload = {
      advice,
      savedAt: new Date().toISOString(),
    }
    window.localStorage.setItem(KEY, JSON.stringify(payload))
    return true
  } catch {
    return false
  }
}

/** Load the cached advice, or null when there is none or it is unreadable. */
export function loadLastAdvice() {
  try {
    const raw = window.localStorage.getItem(KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw)
    if (!parsed || !parsed.advice || !parsed.advice.action) return null
    return parsed
  } catch {
    return null
  }
}

/** How old a cached advice is, in the words a person would use. */
export function describeAge(savedAtIso) {
  const saved = new Date(savedAtIso).getTime()
  if (Number.isNaN(saved)) return null
  const minutes = Math.floor((Date.now() - saved) / 60000)
  if (minutes < 1) return 'अभी'
  if (minutes < 60) return `${minutes} मिनट पहले`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours} घंटे पहले`
  const days = Math.floor(hours / 24)
  return days === 1 ? 'कल' : `${days} दिन पहले`
}
