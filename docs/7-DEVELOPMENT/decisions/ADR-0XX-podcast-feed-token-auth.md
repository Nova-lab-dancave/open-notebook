# ADR-0XX: Podcast feed uses a path token, not the app password

**Status:** Proposed (Nova-Notes fork, 2026-11)

## Context

Issue #31 publishes completed podcast episodes as an RSS feed that Apple Podcasts subscribes to by URL ("Follow a Show by URL"). Apple Podcasts cannot send the app's `Authorization: Bearer` header, so `PasswordAuthMiddleware` would reject every feed and audio request. Apple documents private and password-protected feed URLs as supported, and asks private feeds to carry `<itunes:block>yes</itunes:block>`.

Open Notebook runs on a tailnet-only host. Tailscale Serve already provides HTTPS and the Next.js proxy forwards `/api/*`, so the feed is reachable on the tailnet without new infrastructure. A public Cloudflare tunnel route is possible later and must not change the code.

## Decision

- One Podcast Feed for the whole instance, containing Published Episodes only. Publishing is manual and reversible.
- One Feed Token per instance (`secrets.token_urlsafe(32)`), stored in a singleton settings record and shown in the UI with a Rotate action.
- The token is a URL **path segment**, never a query parameter:
  `/api/podcasts/feed/{token}/feed.xml` and `/api/podcasts/feed/{token}/episodes/{id}.<ext>`.
- `PasswordAuthMiddleware` skips the `/api/podcasts/feed/` prefix. The routes themselves compare the token in constant time and return a uniform 404 for any wrong token, unknown episode or unpublished episode.
- Access logs redact the token segment.
- Absolute URLs come from `OPEN_NOTEBOOK_PUBLIC_URL`, then `API_URL`, then `X-Forwarded-*`. The first source that is HTTPS wins; non-HTTPS sources are skipped. With none, the feed route returns a configuration error (422) that names `OPEN_NOTEBOOK_PUBLIC_URL`, and the UI shows the reason instead of a URL. The token check runs first, so a wrong token is always the uniform 404.
- Only `.mp3` and `.m4a` can be published. `Content-Type` comes from the extension. Range requests are supported.
- Publication state is three nullable fields on `episode` (`published_at`, `duration_seconds`, `feed_summary`), added by fork migration 106 (ADR-014 track).

## Consequences

- Holding the feed URL is the only credential. A leaked URL exposes Published Episodes, never the rest of the app. Rotating the token fixes a leak and breaks every existing subscription.
- The prefix exclusion is the first auth bypass that is not an exact path. Anything added under `/api/podcasts/feed/` is public to token holders and needs the same token check.
- Tailscale Serve and Cloudflare logs still see the token. Redaction covers application logs only.
- Unpublishing removes an episode from the feed at once. Apps that already downloaded it keep their copy.
- Moving to a public hostname later is configuration plus an ingress rule limited to `^/api/podcasts/feed/`, with rate limiting at the edge.

## Alternatives considered

- HTTP basic auth on feed and audio: supported by Apple but less reliable across devices.
- Query-string token: leaks into more logs and referrers.
- Copying audio to a separate static host: a second service to run, and unpublish would not take effect at once.
