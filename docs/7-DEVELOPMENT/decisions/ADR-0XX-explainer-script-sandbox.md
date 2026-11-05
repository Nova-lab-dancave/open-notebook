# ADR-0XX: Generated explainers may run scripts, in a no-network sandbox

- **Status**: Accepted
- **Date**: 2026-11
- **Related**: #19 (Generate Explainer), migration 103 (note files), migration 104

## Context
"Generate Explainer" asks the chat model for one interactive HTML page (tabs, steppers, quizzes, clickable diagrams), so the page needs JavaScript. Until now every HTML note was shown in an iframe with an empty `sandbox` and served with `CSP: sandbox`, so no script could ever run. The model's output is not trusted either: source text from web pages can carry prompt injection, so the generated code must not be able to reach the app, the API token, or the network.

## Decision
- A note flagged `explainer` (set only by the server-side generator, never by an upload) is shown in an iframe with `sandbox="allow-scripts"` and **without** `allow-same-origin`. Scripts run in an opaque origin: no access to the app's DOM, `localStorage` (where the auth token lives), cookies or same-origin API calls.
- Before saving, the generator injects a CSP `<meta>` as the first element of `<head>`: `default-src 'none'`, inline scripts/styles only, `data:` images/fonts/media, `connect-src`, `form-action` and `base-uri` `'none'`. CSPs combine restrictively, so a policy the model writes cannot loosen it. The same policy, plus `sandbox allow-scripts`, is sent as a header when the file is served, and still applies to a downloaded copy opened from disk.
- Uploaded HTML keeps the fully locked sandbox. The flag is the only switch.
- The viewer never opens an explainer's blob URL in a new tab (a blob URL created by the app has the app's origin).

## Alternatives considered
- Static explainers (no JavaScript): safe but loses the interactivity that is the point of the feature.
- Serving explainers from a separate origin: strongest isolation, but needs a second host/port and config for a self-hosted single-user app; the opaque-origin sandbox gives the same isolation from the app without it.
- Sanitising the generated HTML: an allow-list sanitiser would strip the scripts we want, and blacklist sanitising of scripts is unreliable.

## Consequences
- Explainers work offline but cannot use CDNs, web fonts or remote images; the prompt tells the model so.
- Anything that sets `explainer` on a note must only do so for server-generated HTML. A future "import explainer" feature would need its own decision.
- If the viewer ever adds `allow-same-origin` or opens explainers top-level, this record is broken; tests cover the served CSP header.
