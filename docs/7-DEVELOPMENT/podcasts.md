# Podcast Subsystem

How podcast generation is modeled and executed: the two-tier profile system, the model-registry references, and the deliberate no-auto-retry policy.

## Two-tier profile system (`open_notebook/podcasts/models.py`)

- **SpeakerProfile** — voice configuration: a `voice_model` (`record<model>` reference for TTS) plus 1–4 speakers (name, voice_id, backstory, personality). Individual speakers can override the profile's `voice_model`.
- **EpisodeProfile** — generation settings: `outline_llm` / `transcript_llm` (`record<model>` references), `language` (BCP 47, e.g. `pt-BR`), segment count (3–20), briefing template. It references a SpeakerProfile by name.
- **PodcastEpisode** — a generated episode. Links content, profiles and the async job (`command` field → surreal-commands RecordID).

## Model registry references, not strings

Profile fields reference `Model` records instead of raw provider/model strings. At generation time `_resolve_model_config(model_id)` loads the Model, resolves its linked credential (or falls back to `provision_provider_keys()`), and returns `(provider, model_name, config)` for podcast-creator.

The legacy string fields (`tts_provider`, `outline_provider`, …) that predated the registry were dropped by SQL migration 22 (#1107). The migration best-effort maps any still-unresolved profile to an existing `model` record (provider + name + type) before dropping the columns; profiles with no matching record stay unresolved — the UI already flags them as needing model selection and the user re-picks once. The old startup data migration (`open_notebook/podcasts/migration.py`) is gone.

## Profile snapshots

`PodcastEpisode` stores `episode_profile` and `speaker_profile` as **dicts (snapshots)**, not references. Editing a profile never retroactively changes past episodes — that's intentional. Corollary: deleting a profile does not cascade to episodes.

## Prompt templates shadow podcast-creator's

`prompts/podcast/{outline,transcript}.jinja` are **not** just this app's copies of the library's prompts — they replace them. podcast-creator resolves templates as inline config → `prompts_dir` config → `Path.cwd()/prompts/podcast/<name>.jinja` → its own package resources, and this app configures only profiles, so the working directory wins and the bundled prompts are never read.

Consequences to keep in mind when touching these files:

- Library prompt improvements are invisible here. The `{{ language }}` block was lost exactly this way, which made `EpisodeProfile.language` silently do nothing (#1238). `tests/test_podcast_prompt_templates.py` fails when a variable the bundled template uses is missing from the app's copy.
- The variables available are whatever `podcast_creator.nodes` passes: the transcript template gets `speaker_names`, the outline template does **not**.
- Never show the model a fill-in skeleton it can return verbatim. Placeholders (`...`, `[like this]`, `<like this>`) are banned explicitly — a copied `"speaker": "..."` used to abort the whole episode on podcast-creator's speaker-name validation, discarding the segments already generated. The two examples differ: the **transcript** one carries the episode's real speaker names (serialized with `tojson`, so a name containing a quote can't break the example) plus fully written sample dialogue, while the **outline** one has fixed sample segment values — `speaker_names` isn't passed to that template and it has no dialogue. Both are labelled as excerpts (two entries; one for a solo transcript) and restate the required `turns` / `num_segments` count, so each entry's shape is valid to reuse while the excerpt itself can't pass as a complete answer (an outline needs at least three segments). **A sample can only be hard-coded English, so none is rendered when the episode profile sets a non-English `language`** — the structure is stated in prose there, and the schema still reaches the model through `format_instructions`.

## Job lifecycle and the retry policy

Generation runs as a `generate_podcast_command` job on the surreal-commands worker:

- The command resolves model configs and credentials for **all** profiles before invoking podcast-creator, and validates that `outline_llm`, `transcript_llm` and `voice_model` are set.
- **`max_attempts: 1` — no automatic retries.** A mid-generation retry would create duplicate episode records (records are created during execution). Failed episodes are marked `failed` with an error message; retry is explicitly user-initiated via `POST /podcasts/episodes/{id}/retry`.
- Status tracking: `get_job_status()` / `get_job_detail()` query surreal-commands and return `"unknown"` on failure rather than raising. Listing endpoints use the batched `get_job_details_for_commands()` so N episodes cost one status query, not N.
- TTS failures fall back to silent audio rather than failing the episode.

## Podcast Feed

Completed episodes can be published into one private RSS feed that Apple Podcasts (or any podcast app) follows by URL. Terms (Podcast Feed, Published Episode, Feed Token, Show Metadata) are defined in [CONTEXT.md](../../CONTEXT.md); the auth decision is [ADR-0XX: The Podcast Feed authenticates with a token in the URL path](decisions/ADR-0XX-podcast-feed-token-auth.md).

### Routes

| Route | Auth | What it does |
|---|---|---|
| `POST /api/podcasts/episodes/{id}/publish` (body `{summary?}`) | app password | Publish a completed episode; idempotent |
| `POST /api/podcasts/episodes/{id}/unpublish` | app password | Take it out of the feed; a no-op if it is not in it |
| `GET /api/podcasts/feed-url` | app password | The full feed URL, or 422 naming `OPEN_NOTEBOOK_PUBLIC_URL` when no HTTPS origin exists |
| `POST /api/podcasts/feed-token/rotate` | app password | New Feed Token, returns the new URL; refuses (422) instead of rotating blind when no URL can be built |
| `GET`/`PUT /api/podcasts/feed-settings` | app password | Show title, author, description, language (blank = default; a refused edit changes nothing) |
| `POST /api/podcasts/feed-settings/artwork`, `GET .../artwork` | app password | Upload / preview the show artwork |
| `GET`/`HEAD /api/podcasts/feed/{token}/feed.xml` | token in path | The feed |
| `GET`/`HEAD /api/podcasts/feed/{token}/episodes/{id}.{mp3,m4a}` | token in path | Episode audio, with byte ranges |
| `GET`/`HEAD /api/podcasts/feed/{token}/artwork.{png,jpg}?v=` | token in path | Show artwork |

Episode list and detail responses carry `published_at`, `duration_seconds` and `feed_summary`.

### Auth bypass and the Feed Token

- A podcast app cannot send the password, so `PasswordAuthMiddleware` takes an `excluded_prefixes` list (set in `api/main.py`) next to its exact-match `excluded_paths`. Only `/api/podcasts/feed/` is in it, with the trailing slash so `/api/podcasts/feed-url` stays protected. **Every route added under that prefix must call `_require_feed_token`** (`api/routers/podcast_feed.py`).
- The token is `secrets.token_urlsafe(32)` on the singleton `PodcastFeedSettings` record. `PodcastFeedSettings.ensure_feed_token()` mints it once and the API's startup calls it after migrations; `rotate_feed_token()` replaces it. It is compared in constant time.
- A wrong token, no token configured, an unknown or unpublished episode, an extension that differs from the file, a missing file and a path outside the podcasts folder all return the same `404 {"detail": "Not found"}`.
- `api/logging_filters.py` (`RedactFeedToken`) is installed on uvicorn's access logger at startup and rewrites `/api/podcasts/feed/<token>/` to `/api/podcasts/feed/<redacted>/`. Tailscale Serve, the Next.js proxy and any tunnel keep their own logs.
- The settings record is a per-process singleton, so rotate and edits reach other API workers only after a restart. Run one API process.

### Absolute URLs

`resolve_public_base_url` (`open_notebook/podcasts/feed.py`) takes the first HTTPS value of `OPEN_NOTEBOOK_PUBLIC_URL`, then `API_URL`, then the request's `X-Forwarded-Proto`/`X-Forwarded-Host`. Non-HTTPS values are skipped and, with none left, `ConfigurationError` (422) is raised. The token check runs first, so a wrong token is a 404 even with no base URL.

### Publishing rules (`open_notebook/podcasts/publishing.py`)

- Publishable: job completed (or an import with no job), audio path resolves inside the podcasts folder, the file exists, extension `.mp3` or `.m4a`, and `mutagen` can read it. Each refusal is a 400 with its own message.
- Publishing stores `duration_seconds` (`mutagen`), `feed_summary` and `published_at`. The summary is the edited text (up to 4000 characters) or, on a first publish, a 300-character excerpt of the outline's segment descriptions cut at a word boundary (the episode name when there is no outline). The generation briefing is never used. A republish keeps `published_at`, so the pubDate does not move; unpublish then publish gives a new one.
- Deleting an episode removes it from the feed. Retry only accepts failed episodes, so a published one cannot be retried.
- Feed items: title, description, `pubDate`, a stable non-permalink GUID (`open-notebook-episode-<id>`), the enclosure (URL, byte length, MIME type) and `itunes:duration`, newest published first. An episode whose audio vanished is left out and logged. The channel carries `itunes:block` = `yes`, so Apple's public directory never indexes it.
- **Gotcha:** the three publication fields are in `PodcastEpisode.nullable_fields`, so `save()` writes them even when they are `None`. Saving a stale copy of a published episode would unpublish it; load fresh before saving.

### Show Metadata and artwork

Title, author, description, language and the artwork live on the same `PodcastFeedSettings` record; unset means the default (`open_notebook/podcasts/feed.py`). Artwork (`open_notebook/podcasts/artwork.py`) must be a square PNG or JPEG of 1400 to 3000 px, up to 10 MB. Pillow reads only the header (`Image.open`) and `verify()` catches damaged files; the format comes from the content, never the file name. The original bytes are stored untouched at `<podcasts folder>/feed/artwork.png|jpg`, and the feed URL carries `?v=<content hash>` so podcast apps refetch a replaced image. A record whose file is gone counts as no artwork, and the feed then omits it.

### Migration 106

Fork migration 106 (ADR-014 track) adds `published_at` (datetime), `duration_seconds` (int, `>= 0`) and `feed_summary` (string), all optional, to the SCHEMAFULL `episode` table; `106_down.surrealql` removes them. Show Metadata and the token live on the schemaless `open_notebook` table and need no migration.

### Tests

`tests/test_podcast_feed.py` (feed, items, token, auth bypass, base URL, startup minting), `test_podcast_feed_audio.py` (audio, ranges, uniform 404s), `test_podcast_publish.py` (publish rules, summaries, unpublish), `test_podcast_feed_url.py` (feed URL and rotation), `test_podcast_feed_settings.py` (Show Metadata, artwork), `test_log_redaction.py`, and the 106 assertions in `test_migration_tracks.py`. Frontend: `FeedUrlPanel`, `FeedSettingsForm` and `EpisodePublishControl` component tests and `use-podcasts-publish.test.tsx`.
