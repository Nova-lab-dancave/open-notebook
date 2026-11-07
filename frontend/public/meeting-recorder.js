/* Bounded mono PCM capture. No audio is written to browser storage. */
class MeetingPCMRecorder extends AudioWorkletProcessor {
  constructor() {
    super()
    this.buffer = new Float32Array(sampleRate * 20)
    this.length = 0
    this.active = true
    this.port.onmessage = (event) => {
      if (event.data === 'stop') {
        this.flush()
        this.active = false
        this.port.postMessage({ stopped: true })
      }
    }
  }
  flush() {
    if (!this.length) return
    const pcm = this.buffer.slice(0, this.length)
    this.port.postMessage({ pcm }, [pcm.buffer])
    this.length = 0
  }
  process(inputs) {
    if (!this.active) return false
    const channels = inputs[0]
    if (channels?.length) {
      for (let i = 0; i < channels[0].length; i++) {
        let sample = 0
        for (const channel of channels) sample += channel[i] / channels.length
        this.buffer[this.length++] = sample
        if (this.length === this.buffer.length) this.flush()
      }
    }
    return true
  }
}
registerProcessor('meeting-pcm-recorder', MeetingPCMRecorder)
