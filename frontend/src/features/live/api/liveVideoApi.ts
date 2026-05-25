const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

export const LIVE_VIDEO_TRANSPORT = (
  import.meta.env.VITE_LIVE_VIDEO_TRANSPORT ?? 'webrtc'
).toLowerCase()

export function resolveMediaUrl(imageUrl: string) {
  if (!imageUrl) {
    return ''
  }
  if (imageUrl.startsWith('http://') || imageUrl.startsWith('https://')) {
    return imageUrl
  }
  return `${API_BASE_URL}${imageUrl}`
}

export function resolveWebRtcOfferUrl(cameraId: string) {
  return `${API_BASE_URL}/media/live/${encodeURIComponent(cameraId)}/webrtc/offer`
}
