/**
 * The only place the browser talks to our API.
 *
 * Errors are classified rather than collapsed, because the screen has to say
 * three different things: "we cannot reach the service", "that village is not
 * known", and "you are offline but here is your last advice". A single
 * "something went wrong" would leave a farmer unable to tell a dead connection
 * from a typo.
 */

const TIMEOUT_MS = 15000

export class ApiError extends Error {
  constructor(kind, message, detail) {
    super(message)
    this.name = 'ApiError'
    this.kind = kind // 'offline' | 'upstream' | 'invalid' | 'unknown'
    this.detail = detail
  }
}

async function request(path, options = {}) {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS)

  let response
  try {
    response = await fetch(path, { ...options, signal: controller.signal })
  } catch (error) {
    // A stopped backend, aeroplane mode, or a dropped 3G signal all land here.
    throw new ApiError(
      'offline',
      'इंटरनेट या सर्वर से संपर्क नहीं हो पाया।',
      error.message,
    )
  } finally {
    clearTimeout(timer)
  }

  if (!response.ok) {
    let detail = ''
    try {
      const body = await response.json()
      detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail)
    } catch {
      detail = response.statusText
    }
    if (response.status === 422) {
      throw new ApiError('invalid', 'दर्ज की गई जानकारी ठीक नहीं है।', detail)
    }
    if (response.status === 502) {
      throw new ApiError(
        'upstream',
        'मौसम सेवा अभी जवाब नहीं दे रही है।',
        detail,
      )
    }
    throw new ApiError('unknown', 'कुछ गड़बड़ हो गई।', detail)
  }

  return response.json()
}

/** Search Indian villages and towns by name. */
export async function searchLocations(query) {
  const body = await request(
    `/api/locations/search?q=${encodeURIComponent(query)}&limit=6`,
  )
  return body.results
}

/** Ask for the one decision the app exists to give. */
export async function fetchAdvice({ crop, sowingDate, location, lastIrrigationDate }) {
  return request('/api/advice', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      crop,
      sowing_date: sowingDate,
      latitude: location.latitude,
      longitude: location.longitude,
      location_name: location.display_name,
      // Omitted rather than sent as a guess when the farmer leaves it blank:
      // the backend then reports that it assumed no irrigation, which the card
      // shows, instead of the app inventing a date for them.
      last_irrigation_date: lastIrrigationDate || null,
    }),
  })
}
