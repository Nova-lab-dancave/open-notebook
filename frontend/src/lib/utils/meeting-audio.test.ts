import { expect, it } from 'vitest'
import { encodeMeetingWav } from './meeting-audio'
it('encodes an independent mono PCM WAV with correct sample rate and clipped samples', async () => {
  const blob = encodeMeetingWav(new Float32Array([-2, -0.5, 0, 0.5, 2]), 16000)
  const buffer = await new Promise<ArrayBuffer>((resolve) => {
    const reader = new FileReader()
    reader.onload = () => resolve(reader.result as ArrayBuffer)
    reader.readAsArrayBuffer(blob)
  })
  const data = new DataView(buffer)
  expect(blob.type).toBe('audio/wav')
  expect(blob.size).toBe(54)
  expect(data.getUint32(4, true)).toBe(46)
  expect(data.getUint16(20, true)).toBe(1)
  expect(data.getUint16(22, true)).toBe(1)
  expect(data.getUint32(24, true)).toBe(16000)
  expect(data.getUint32(40, true)).toBe(10)
  expect([0, 1, 2, 3, 4].map((i) => data.getInt16(44 + i * 2, true))).toEqual([-32768, -16384, 0, 16383, 32767])
})

it('worklet emits exact twenty-second windows and flushes the last partial window', async () => {
  const { readFileSync } = await import('node:fs')
  const { runInNewContext } = await import('node:vm')
  const posted: Array<{ pcm?: Float32Array; stopped?: boolean }> = []
  interface Worklet {
    port: { onmessage: (event: { data: string }) => void }
    process: (inputs: Float32Array[][]) => boolean
  }
  let Recorder: new () => Worklet = class {
    port = { onmessage: () => {} }
    process = () => true
  }
  runInNewContext(readFileSync('public/meeting-recorder.js', 'utf8'), {
    AudioWorkletProcessor: class { port = { postMessage: (message: typeof posted[number]) => posted.push(message) } },
    sampleRate: 10,
    Float32Array,
    registerProcessor: (_name: string, constructor: typeof Recorder) => { Recorder = constructor },
  })
  const recorder = new Recorder()
  const input = [new Float32Array(128).fill(1), new Float32Array(128).fill(3)]
  recorder.process([input]); recorder.process([input])
  expect(posted).toHaveLength(1)
  expect(posted[0].pcm?.length).toBe(200)
  expect(Array.from(posted[0].pcm ?? []).every((value) => value === 2)).toBe(true)
  recorder.port.onmessage({ data: 'stop' })
  expect(posted[1].pcm?.length).toBe(56)
  expect(posted[2]).toEqual({ stopped: true })
  expect(recorder.process([input])).toBe(false)
})
