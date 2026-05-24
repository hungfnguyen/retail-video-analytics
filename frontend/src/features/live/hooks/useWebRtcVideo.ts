import { useEffect, useRef, useState } from 'react'
import type { RefObject } from 'react'
import { resolveWebRtcOfferUrl } from '../api/liveVideoApi'

type WebRtcVideoState = {
  fallbackRequired: boolean
  videoRef: RefObject<HTMLVideoElement | null>
}

async function waitForIceGatheringComplete(peerConnection: RTCPeerConnection) {
  if (peerConnection.iceGatheringState === 'complete') {
    return
  }

  await new Promise<void>((resolve) => {
    const timeoutId = window.setTimeout(resolve, 1500)

    function handleStateChange() {
      if (peerConnection.iceGatheringState === 'complete') {
        window.clearTimeout(timeoutId)
        peerConnection.removeEventListener('icegatheringstatechange', handleStateChange)
        resolve()
      }
    }

    peerConnection.addEventListener('icegatheringstatechange', handleStateChange)
  })
}

function clearVideoElement(videoElement: HTMLVideoElement | null) {
  if (!videoElement?.srcObject) {
    return
  }

  const stream = videoElement.srcObject as MediaStream
  stream.getTracks().forEach((track) => track.stop())
  videoElement.srcObject = null
}

export function useWebRtcVideo(cameraId: string, enabled: boolean): WebRtcVideoState {
  const videoRef = useRef<HTMLVideoElement | null>(null)
  const [fallbackRequired, setFallbackRequired] = useState(!enabled)

  useEffect(() => {
    const videoElement = videoRef.current

    if (!enabled) {
      clearVideoElement(videoElement)
      return
    }

    let cancelled = false
    const abortController = new AbortController()
    const peerConnection = new RTCPeerConnection()

    async function connect() {
      try {
        setFallbackRequired(false)
        peerConnection.addTransceiver('video', { direction: 'recvonly' })

        peerConnection.ontrack = (event) => {
          if (cancelled || !videoRef.current) {
            return
          }
          videoRef.current.srcObject = event.streams[0]
        }

        peerConnection.onconnectionstatechange = () => {
          if (cancelled) {
            return
          }
          if (['failed', 'closed', 'disconnected'].includes(peerConnection.connectionState)) {
            setFallbackRequired(true)
          }
        }

        const offer = await peerConnection.createOffer()
        await peerConnection.setLocalDescription(offer)
        await waitForIceGatheringComplete(peerConnection)

        if (!peerConnection.localDescription) {
          throw new Error('Missing local WebRTC description.')
        }

        const response = await fetch(resolveWebRtcOfferUrl(cameraId), {
          body: JSON.stringify({
            sdp: peerConnection.localDescription.sdp,
            type: peerConnection.localDescription.type,
          }),
          headers: { 'Content-Type': 'application/json' },
          method: 'POST',
          signal: abortController.signal,
        })

        if (!response.ok) {
          throw new Error('WebRTC offer was rejected.')
        }

        const answer = (await response.json()) as RTCSessionDescriptionInit
        if (cancelled) {
          return
        }

        await peerConnection.setRemoteDescription(answer)
      } catch (error) {
        if (!cancelled && !(error instanceof DOMException && error.name === 'AbortError')) {
          setFallbackRequired(true)
          peerConnection.close()
        }
      }
    }

    void connect()

    return () => {
      cancelled = true
      abortController.abort()
      clearVideoElement(videoElement)
      peerConnection.close()
    }
  }, [cameraId, enabled])

  return { fallbackRequired: !enabled || fallbackRequired, videoRef }
}
