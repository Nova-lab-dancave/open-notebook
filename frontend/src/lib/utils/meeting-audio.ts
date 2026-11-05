/** Encode independent WAV files; MediaRecorder timeslices are not standalone audio. */
export function encodeMeetingWav(samples: Float32Array, rate: number): Blob {
  const buffer = new ArrayBuffer(44 + samples.length * 2)
  const view = new DataView(buffer)
  const text = (offset: number, value: string) => {
    for (let i = 0; i < value.length; i++) view.setUint8(offset + i, value.charCodeAt(i))
  }
  text(0, 'RIFF'); view.setUint32(4, buffer.byteLength - 8, true)
  text(8, 'WAVE'); text(12, 'fmt '); view.setUint32(16, 16, true)
  view.setUint16(20, 1, true); view.setUint16(22, 1, true)
  view.setUint32(24, rate, true); view.setUint32(28, rate * 2, true)
  view.setUint16(32, 2, true); view.setUint16(34, 16, true)
  text(36, 'data'); view.setUint32(40, samples.length * 2, true)
  samples.forEach((sample, i) => {
    const value = Math.max(-1, Math.min(1, sample))
    view.setInt16(44 + i * 2, value < 0 ? value * 32768 : value * 32767, true)
  })
  return new Blob([buffer], { type: 'audio/wav' })
}

export type MeetingCapture = {
  stop: () => Promise<boolean>
  start: (chunk: (audio: Blob) => void, ended: () => void) => Promise<void>
}

/** Permissions happen on the click, before a meeting is created on the server. */
export async function prepareMeetingCapture(shared: boolean): Promise<MeetingCapture> {
  const streams: MediaStream[] = []
  let context: AudioContext | undefined
  let node: AudioWorkletNode | undefined
  let stopping: Promise<boolean> | undefined
  const cleanup = () => {
    for (const stream of streams) for (const track of stream.getTracks()) track.stop()
    node?.disconnect()
    if (context && context.state !== 'closed') void context.close()
  }
  try {
    if (shared) {
      const display = await navigator.mediaDevices.getDisplayMedia({ video: true, audio: true })
      streams.push(display)
      if (!display.getAudioTracks().length) throw new Error('meetings.noSharedAudio')
    }
    streams.push(await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true, channelCount: 1 },
    }))
    context = new AudioContext({ sampleRate: 16000 })
    await context.audioWorklet.addModule('/meeting-recorder.js')
    node = new AudioWorkletNode(context, 'meeting-pcm-recorder')
    const captureContext = context
    const captureNode = node
    return {
      start: async (chunk, ended) => {
        captureNode.port.onmessage = (event) => {
          if (event.data.pcm) chunk(encodeMeetingWav(event.data.pcm, captureContext.sampleRate))
        }
        for (const stream of streams) {
          const audioOnly = new MediaStream(stream.getAudioTracks())
          captureContext.createMediaStreamSource(audioOnly).connect(captureNode)
          for (const track of stream.getTracks()) track.onended = ended
        }
        const silent = captureContext.createGain()
        silent.gain.value = 0
        captureNode.connect(silent).connect(captureContext.destination)
        await captureContext.resume()
      },
      stop: () => {
        if (stopping) return stopping
        stopping = new Promise<boolean>((resolve) => {
          const previous = captureNode.port.onmessage
          const timeout = window.setTimeout(() => { cleanup(); resolve(false) }, 2000)
          captureNode.port.onmessage = (event) => {
            if (event.data.stopped) {
              window.clearTimeout(timeout)
              cleanup()
              resolve(true)
            } else previous?.call(captureNode.port, event)
          }
          captureNode.port.postMessage('stop')
        })
        return stopping
      },
    }
  } catch (error) {
    cleanup()
    throw error
  }
}
