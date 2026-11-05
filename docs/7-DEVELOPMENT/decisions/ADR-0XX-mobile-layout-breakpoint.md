# ADR-0XX: Mobile layout is chosen by CSS, below `lg` or on touch tablets up to 1199 px

- **Status**: Accepted
- **Date**: 2026-11
- **Related**: #30 (mobile UI), #21 (meeting transcription)

## Context
#30 asks for a mobile UI on iPhone and iPad mini: no sidebar, a bottom menu bar instead. iPad mini is 744 px wide in portrait but 1133 px in landscape, so the existing `lg` (1024 px) width breakpoint alone would give landscape iPad mini the desktop layout with the sidebar. The app's only existing switch (`useIsDesktop`, a JS media-query hook) returns `false` until it runs on the client, which would flash the wrong shell on load.

## Decision
- A Tailwind custom variant `mobile:` in `globals.css` matches `(max-width: 1023.98px)` **or** `(pointer: coarse) and (max-width: 1199.98px)`. The second query covers touch tablets up to iPad Air / iPad Pro 11" landscape (1180-1194 px), iPad mini in both orientations included; a 12.9" iPad Pro in landscape (1366 px) keeps the desktop layout.
- The app shell renders both the sidebar and the bottom bar and lets `mobile:hidden` / `hidden mobile:grid` pick one, so the right shell is there on first paint with no hydration mismatch.
- Page-level layouts are unchanged: the notebook page still switches to tabs below `lg`, so a landscape iPad mini gets the three-column notebook without the sidebar.
- The bar height is one CSS variable (`--mobile-bar-height`); `main` and the podcast mini-player offset by it plus `env(safe-area-inset-bottom)`, which needs `viewport-fit=cover`.

## Alternatives considered
- Width only at `lg`: misses landscape iPad mini, which #30 names.
- User-agent sniffing: unreliable (iPadOS reports a desktop Safari UA) and server-side only.
- A JS hook for the shell: flashes the desktop sidebar before hydration on every load.

## Consequences
- Touch laptops narrower than 1200 px with a coarse primary pointer also get the mobile shell; acceptable, as it is usable with a pointer too.
- New components that need the same split should use the `mobile:` variant, not a new media query.
