/**
 * Hindi (and English) speech out, using the browser's own speech synthesis.
 *
 * No audio files and no network: the phone already knows how to talk, so the
 * app sends it text. That keeps the data cost of listening effectively zero,
 * which matters for the farmer this is built for.
 *
 * Everything here degrades quietly. Voice support is patchy — a laptop may
 * have no Hindi voice at all — so `speak` returns false rather than throwing,
 * and the screen shows the text regardless. The advice must never depend on
 * whether a voice happens to be installed.
 */

const LANG = {
  hi: 'hi-IN',
  en: 'en-IN',
}

/** True when this browser can speak at all. */
export function speechSupported() {
  return typeof window !== 'undefined' && 'speechSynthesis' in window
}

/**
 * Pick a voice for a language, preferring a real match over a default.
 * Returns null when the platform offers nothing for that language, which is
 * common for Hindi on desktop Linux and older Android.
 */
function pickVoice(lang) {
  if (!speechSupported()) return null
  const voices = window.speechSynthesis.getVoices()
  if (!voices.length) return null
  const exact = voices.find((v) => v.lang === lang)
  if (exact) return exact
  const prefix = lang.split('-')[0]
  return voices.find((v) => v.lang && v.lang.toLowerCase().startsWith(prefix)) || null
}

/** Whether a voice exists for a language, so the UI can hide a dead button. */
export function hasVoiceFor(language) {
  return Boolean(pickVoice(LANG[language] || LANG.hi))
}

/**
 * Speak a sentence. Any previous utterance is cancelled first, so pressing the
 * button twice does not queue the same advice up twice — the second press
 * restarts it instead.
 */
export function speak(text, language = 'hi') {
  if (!speechSupported() || !text) return false
  try {
    window.speechSynthesis.cancel()
    const utterance = new SpeechSynthesisUtterance(text)
    utterance.lang = LANG[language] || LANG.hi
    const voice = pickVoice(utterance.lang)
    if (voice) utterance.voice = voice
    // Slightly slower than default: a phone held at arm's length in a field
    // benefits from the extra moment per sentence.
    utterance.rate = 0.92
    utterance.pitch = 1
    window.speechSynthesis.speak(utterance)
    return true
  } catch {
    return false
  }
}

/** Stop speaking, e.g. when the language toggle is flipped or the result clears. */
export function stopSpeaking() {
  if (!speechSupported()) return
  try {
    window.speechSynthesis.cancel()
  } catch {
    /* nothing to stop */
  }
}
