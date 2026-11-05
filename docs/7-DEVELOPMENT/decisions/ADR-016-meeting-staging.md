# ADR-016: Browser meeting capture and isolated transcript staging

**Status:** Accepted (Nova-Notes fork, issue #21)

## Context

Meeting transcripts need review before becoming notebook knowledge. Ordinary
`Note.save()` submits embeddings immediately, and notes participate in chat and
search through several independent paths. A flag filtered in only the Notes pane
would not isolate a draft. We also need meeting audio without retaining recordings.

FluidVoice's current meeting implementation is native macOS Swift under GPLv3.
This implementation was written independently for the existing MIT application;
no FluidVoice source, prompts, assets or dependencies are incorporated.

## Decision

- Browser `getUserMedia` captures the microphone. Optional `getDisplayMedia`
  captures shared audio, with an explicit failure if no audio track was granted.
  Capture requires HTTPS or localhost. System audio support varies by browser,
  operating system and selected surface; microphone-only remains available.
- Web Audio mixes the sources. An AudioWorklet emits exact twenty-second mono
  blocks and flushes a shorter final block. Each block is encoded as a complete
  PCM WAV; MediaRecorder timeslices are unsuitable because later slices may lack
  the container header needed by transcription providers.
- At most six chunks wait for transcription. If providers fall behind, stop
  recording and drain the queue, marking dropped sections as missing. Sessions
  stop after four hours. Requests have a ninety-second transcription timeout.
- The API uses the configured default speech-to-text model. Audio is held in
  browser memory and a private backend temporary directory only; files are
  removed on completion, failure or cancellation. No audio is put in command
  arguments, database records, browser storage, notes or persistent uploads.
  A process crash can interrupt cleanup; this is not a secure-erasure guarantee.
  Provider retention is governed by the selected provider's policies.
- Fork migration 105 introduces `meeting` and `meeting_chunk`. Drafts have no
  artifact relationship or embedding. A unique meeting/sequence index prevents
  duplicate transcript chunks. Allocated sequence slots survive provider failure.
  Finalization explicitly labels absent slots and preserves completed text.
- Summary generation runs through surreal-commands and the shared chat-model
  provisioner. Structured actions require an exact transcript quotation; owners
  and dates are left blank when unstated. Text is untrusted evidence, not prompt
  instructions. Missing or malformed output fails visibly and can be retried.
- A generation token prevents delayed workers overwriting edits. A revision
  check protects publication and edits from stale writes. Approval atomically
  creates a deterministic normal note, links it to the notebook and marks the
  meeting approved. Only then is embedding submitted. Repeated approval returns
  the existing note. Editing approved meeting fields updates its note atomically.
- Discard and notebook deletion remove draft transcript chunks. Deleting an
  approved note removes its retained meeting record too. Rollback drops draft
  tables and preserves approved notes; back up drafts before rollback.

## Consequences

No native helper or new runtime dependency is needed. Live text arrives after
each completed chunk, rather than word by word. Browser capture cannot guarantee
recording arbitrary desktop meeting applications. There is no automatic speaker
identification, calendar integration or external task publication. A terminated
browser cannot preserve unsent audio; recovery clearly warns about the final
section. Large transcripts require a chat model with sufficient context.
