# ADR-0XX: Podcast feed uses a path token, not the app password

**Status:** Proposed (Nova-Notes fork, 2026-11)

## Context

Issue #31 publishes completed podcast episodes as an RSS feed that Apple Podcasts subscribes to by URL ("Follow a Show by URL"). Apple Podcasts cannot send the app's `Authorization: Bearer` header, so `PasswordAuthMiddleware` would reject every feed and audio request. Apple documents private and password-protected feed URLs as supported, and asks private feeds to carry `<itunes:block>yes</itunes:block>`.

Open Notebook runs on a tailnet-only host. Tailscale Serve already provides HTTPS and the Next.js proxy forwards `/api/*`, so the feed is reachable on the tailnet without new infrastructure. A public Cloudflare tunnel route is possible later and must not change the code.

## Decision

- One Podcast Feed for the whole instance, containing Published Episodes only. Publishing is manual and reversible.
- One Feed Token per instance (`secrets.token_urlsafe(32)`), minted once at the first API startup after migrations and stored in a singleton settings record. Later startups reuse it; only a rotation replaces it. It is shown in the UI with a Rotate action.
- The token is a URL **path segment**, never a query parameter:
  `/api/podcasts/feed/{token}/feed.xml` and `/api/podcasts/feed/{token}/episodes/{id}.<ext>`.
- `PasswordAuthMiddleware` skips the `/api/podcasts/feed/` prefix. The routes themselves compare the token in constant time and return a uniform 404 for any wrong token, unknown episode or unpublished episode.
- Access logs redact the token segment.
- The UI gets the feed URL from an authenticated `GET /api/podcasts/feed-url` and replaces the token with an authenticated `POST /api/podcasts/feed-token/rotate`. Both sit outside the exempt prefix (so the app password applies), and rotation refuses when no HTTPS origin can be resolved rather than rotating blind.
- Absolute URLs come from `OPEN_NOTEBOOK_PUBLIC_URL`, then `API_URL`, then `X-Forwarded-*`. The first source that is HTTPS wins; non-HTTPS sources are skipped. With none, the feed route returns a configuration error (422) that names `OPEN_NOTEBOOK_PUBLIC_URL`, and the UI shows the reason instead of a URL. The token check runs first, so a wrong token is always the uniform 404.
- Only `.mp3` (`audio/mpeg`) and `.m4a` (`audio/x-m4a`) can be published; the enclosure `Content-Type` comes from the extension. Range requests are supported, and the feed and audio routes answer GET and HEAD. A published episode whose audio file has vanished is left out of the feed rather than served broken.
- Show Metadata (title, author, description, language) and the artwork live on the same singleton settings record as the token; an unset or blank value means the default. The authenticated `GET`/`PUT /api/podcasts/feed-settings` edit them. Artwork is uploaded to the authenticated `POST /api/podcasts/feed-settings/artwork` and stored untouched at `<podcasts folder>/feed/artwork.{png,jpg}`; the feed advertises it at the token-gated `/api/podcasts/feed/{token}/artwork.{ext}?v=<content hash>` (the hash changes the URL so Apple refetches a replaced image) and leaves it out if the file is gone.
- Artwork must be a PNG or JPEG, square, 1400 to 3000 pixels, up to 10 MB. It is checked with Pillow, which is now a declared dependency (it was already locked through `content-core`): `Image.open` reads only the header, `verify()` catches damaged files, and its decompression-bomb guard is handled as a refusal. A hand-written PNG/JPEG header parser was rejected as more code with more ways to be wrong. The format is taken from the file's content, never its name.
- Publication state is three nullable fields on `episode` (`published_at`, `duration_seconds`, `feed_summary`), added by fork migration 106 (ADR-014 track).

## Consequences

- Holding the feed URL is the only credential. A leaked URL exposes Published Episodes, never the rest of the app. Rotating the token fixes a leak and breaks every existing subscription.
- The prefix exclusion is the first auth bypass that is not an exact path. Anything added under `/api/podcasts/feed/` is public to token holders and needs the same token check.
- Tailscale Serve and Cloudflare logs still see the token. Redaction covers application logs only.
- The settings record is cached per API process. Run a single API process (the default); with several workers a rotation only reaches the others after a restart.
- Unpublishing removes an episode from the feed at once. Apps that already downloaded it keep their copy.
- Moving to a public hostname later is configuration plus an ingress rule limited to `^/api/podcasts/feed/`, with rate limiting at the edge.

## Alternatives considered

- HTTP basic auth on feed and audio: supported by Apple but less reliable across devices.
- Query-string token: leaks into more logs and referrers.
- Copying audio to a separate static host: a second service to run, and unpublish would not take effect at once.
