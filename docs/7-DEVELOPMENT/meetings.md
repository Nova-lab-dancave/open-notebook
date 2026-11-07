# Meeting transcription

Issue #21 adds a Meetings panel to a notebook's Notes column.

## Setup and use

Configure a default **speech-to-text** model and a default **chat** model in
Settings. Start SurrealDB, API, background worker, and frontend in that order
(`make start-all`). Migration 105 runs automatically with API startup.

Open the app through HTTPS or localhost. Enter a meeting title, optionally enable
shared audio, and click **Record meeting**. Microphone-only mode suits in-person
meetings. For an online call, Chrome or Edge with a browser meeting tab is the
recommended starting point: select the tab and enable **Share audio** in the
browser's sharing prompt. A screen/window picker does not guarantee audio;
recording fails explicitly when no shared audio track is supplied. Use headphones
to avoid recording speakers through both the microphone and shared stream.
System/desktop audio availability depends on browser and OS. Notify participants
before recording. The selected transcription provider receives the audio; its
retention policy applies. Locally, only text is retained after processing.

Click **Stop** to flush the final audio and finish pending transcriptions. Recording
stops automatically after four hours, when an audio source disconnects, or when
transcription falls more than six chunks behind. Do not close the tab while
finishing. Navigation stops capture and attempts finalization; reloading or closing
can lose unsent audio. **Finish interrupted recording** recovers completed text
and warns about the potentially missing final section.

Review the **Summary / Actions / Transcript** tabs. Transcription gaps are marked,
not filled in. Actions contain a supporting quote, with owners/dates only when
stated. Use **Edit** to correct text and actions or mark actions done, then **Save**.
**Approve for notebook chat** publishes a normal note containing all three sections.
Until approval, the meeting is excluded from note search, embeddings and chat.
No tasks are pushed to another service. **Discard** permanently removes the draft.
Deleting the published note also deletes its retained meeting review record.

## Troubleshooting

- Missing microphone or sharing permission: allow the browser permissions and
  use HTTPS/localhost. Mobile and Safari/Firefox shared-audio support is limited.
- No shared audio: choose a source that offers audio and tick **Share audio**.
  Microphone-only is an explicit alternative, never an automatic fallback.
- Missing sections: provider/network failures are retained as gaps. Successfully
  transcribed sections remain. Audio is not retained for later replay/retry.
- Queued summary: check `make worker-start`. You can edit/approve a transcript
  without waiting for a queued summary. Editing invalidates its old generation.
- Failed summary: check default chat model, credentials and context capacity,
  then use **Generate summary again**. This reuses the saved transcript.
- Audio buffering: recording stops when the six-chunk queue is full, avoiding
  unlimited memory growth. Use a faster transcription model or connection.

## Validation

Unit tests: `uv run pytest tests/test_meetings.py` and, in `frontend/`,
`npm run test -- src/lib/hooks/use-meeting-recorder.test.ts src/lib/utils/meeting-audio.test.ts`.
The opt-in database test creates/removes a unique namespace on an isolated SurrealDB:

```sh
MEETINGS_TEST_DATABASE_URL=ws://localhost:18000/rpc SURREAL_USER=root \
  uv run pytest tests/test_meetings_integration.py
```

Manual browser acceptance: record a mic-only sample, then a shared tab plus mic;
verify both sides appear. Test permission denial, sharing without audio, stopping
sharing, final partial-chunk flush, failed transcription, refresh recovery and
navigation cleanup. Review, edit, approve twice, and verify only one published
note enters chat/search. Confirm temp audio disappears on provider error too.
The automated provider tests use doubles; they do not validate a real provider's
recognition accuracy or a physical microphone/system-audio combination.

See [ADR-016](decisions/ADR-016-meeting-staging.md) for storage and lifecycle decisions.

## Test on a Mac

Use a fresh checkout so the test has its own configuration and database files.
Requirements: Docker Desktop or OrbStack running, Node.js 22, and `uv`. If needed,
install the command-line dependencies with Homebrew:

```sh
brew install uv node@22
export PATH="$(brew --prefix node@22)/bin:$PATH"
```

Clone the meeting branch and install the locked dependencies:

```sh
git clone --branch feat/21-meeting-notes https://github.com/Nova-lab-dancave/open-notebook.git open-notebook-meeting-test
cd open-notebook-meeting-test
uv sync --locked
(cd frontend && npm ci)
```

Create the local configuration below. This command refuses to replace an existing
`.env`; the generated encryption key must be kept to read credentials saved in
this test database. `.env` is ignored by Git.

```sh
uv run python - <<'PY'
import os
import secrets

config = (
    "SURREAL_URL=ws://localhost:8000/rpc\n"
    "SURREAL_USER=root\n"
    "SURREAL_PASSWORD=root\n"
    "SURREAL_NAMESPACE=meeting_test\n"
    "SURREAL_DATABASE=meeting_test\n"
    "API_HOST=127.0.0.1\n"
    "API_PORT=5055\n"
    "API_RELOAD=false\n"
    "OPEN_NOTEBOOK_ENCRYPTION_KEY=" + secrets.token_urlsafe(48) + "\n"
)
with os.fdopen(os.open('.env', os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'w') as f:
    f.write(config)
print('Created private local .env')
PY
API_URL=/. make start-all
```

Leave that terminal running and open **http://localhost:3000** in Chrome or Edge.
The stack uses ports 3000, 5055 and 8000; stop other local instances on those ports
before starting this test. `make start-all` starts only the database container and
runs this branch's API, worker and frontend from source. Do not run plain
`docker compose up`: its application service uses the upstream published image.

1. Open **Models**, add your provider configuration, and assign **Chat Model** and
   **Speech-to-Text Model**. Configure an embedding model too if testing search.
   Enter provider keys in the app, not in a chat or a shared shell transcript.
2. Create a notebook named **Meeting test** and record a microphone-only sample:
   “We agreed to launch on Tuesday. Alice will email the report by Friday. Bob
   will book the review on Monday.” Speak for twenty to thirty seconds, then stop.
3. Verify the transcript, decision summary, and two actions with supporting quotes.
   Check that unstated owners/dates are left blank rather than invented.
4. Edit an action, save, then approve. Verify the published note appears once and
   can be selected as notebook chat context. Verify the action can be checked off
   through the meeting's Edit controls after approval.
5. For shared audio, open a meeting in another browser tab. Enable the shared-audio
   option, select that tab in the browser picker, and enable **Share tab audio**.
   Use headphones. Verify both microphone and remote speech are transcribed.
6. Test sharing without audio or canceling microphone permission; verify a visible
   failure. Stop sharing during recording; verify capture stops and completed text
   remains. Test discard on a draft you no longer need.

macOS may request microphone and Screen & System Audio Recording permissions for
Chrome/Edge. Browser-tab audio is the initial shared-audio test; capturing a native
Zoom/Teams app depends on the available browser/macOS sharing features.

Stop the test stack from a second terminal in this checkout with `make stop-all`.
Keep `.env` and `surreal_data/` together if you want to retain the test credentials
and notes. This test does not migrate or connect to a lab database.
