# ADR-0XX: The Podcast Feed authenticates with a token in the URL path

- **Status**: Accepted
- **Date**: 2026-11
- **Related**: #31, #37, [ADR-014](ADR-014-fork-migration-track.md)

## Context
#31 publishes completed podcast episodes as an RSS feed that Apple Podcasts follows by URL ("Follow a Show by URL"). A podcast app cannot send the app's `Authorization: Bearer` header, so `PasswordAuthMiddleware` would reject every feed and audio request. Apple documents private feed URLs as supported and asks them to carry `<itunes:block>yes</itunes:block>`. Open Notebook runs tailnet-only; Tailscale Serve already gives it HTTPS and forwards `/api/*`. A public hostname (a Cloudflare tunnel route) may come later and must not change the code.

## Decision
- One Podcast Feed for the whole instance, listing Published Episodes only. Publishing is manual and reversible.
- One **Feed Token** per instance (`secrets.token_urlsafe(32)`), minted once at the first API startup and kept on a singleton settings record. It is a URL **path segment** (`/api/podcasts/feed/{token}/...`), never a query parameter. Rotating replaces it.
- The password middleware skips the `/api/podcasts/feed/` prefix. Every route under it checks the token in constant time, and a wrong token, an unknown or unpublished episode and a missing file all return the same 404.
- Absolute URLs come from `OPEN_NOTEBOOK_PUBLIC_URL`, then `API_URL`, then `X-Forwarded-*`. The first HTTPS source wins; with none, the feed answers 422 and the UI explains why instead of showing a URL.
- Application access logs replace the token with `<redacted>`.
- Only `.mp3` and `.m4a` can be published. Show artwork must be a square PNG or JPEG of 1400 to 3000 px, checked with Pillow (already locked through `content-core`, now declared); a hand-written header parser was rejected as more code with more ways to be wrong.
- Publication state is three nullable `episode` fields added by fork migration 106 (ADR-014).

## Alternatives considered
- HTTP basic auth on feed and audio: Apple supports it but less reliably across devices.
- A token in the query string: leaks into more logs and referrers.
- Copying published audio to a separate static host: a second service to run, and unpublish would not take effect at once.

## Consequences
- Holding the feed URL is the only credential. A leaked URL exposes Published Episodes, never the rest of the app. Rotating fixes a leak and breaks every existing subscription.
- This is the first auth bypass that is not an exact path. Anything added under `/api/podcasts/feed/` is open to token holders and must check the token.
- Tailscale Serve and Cloudflare logs still see the token; redaction covers application logs only.
- The settings record is cached per API process, so run one API process (the default). With several, a rotation reaches the others only after a restart.
- Unpublishing removes an episode from the feed at once; apps that already downloaded it keep their copy.
- Going public later is configuration plus an ingress rule limited to `^/api/podcasts/feed/` and edge rate limiting.
