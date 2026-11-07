# ADR-017: Infographics are sanitised static SVG drawn by the chat model

- **Status**: Accepted
- **Date**: 2026-11
- **Related**: #22 (Generate Infographic), ADR-015 (explainer sandbox), migration 103 (note files)

## Context
"Generate Infographic" turns a notebook's sources into a one-page visual summary with a choice of styles. The issue named two bases: `aizzaku/aiz-infographic` (HTML infographics with PNG export, **no licence**, so only its ideas can be used) and `JimLiu/baoyu-skills` (`baoyu-infographic`, **MIT**, 21 layouts x 22 styles, but written for a raster **image-generation model**). The app has no image-generation model type. Infographics should also be downloadable, which explainers deliberately are not (ADR-015).

## Decision
- The default **chat model writes one static SVG** poster. baoyu's layouts and styles (the ones that translate to vector art) are rewritten as prompt guidance in `open_notebook/utils/infographic.py`, with attribution; the frontend offers the same ids (`frontend/src/lib/infographic-options.ts`, cross-checked by a test).
- **Sanitise, don't sandbox.** Unlike explainers, an infographic needs no scripts, so `sanitize_svg()` parses the reply with `defusedxml` (no DTDs or entities) and rebuilds it from an allow-list of drawing, text, gradient, pattern, mask and filter elements. Scripts, `foreignObject`, links, images, animation, event handlers, foreign namespaces and every reference that is not a local `#fragment` (attributes, inline `style`, `<style>`) are dropped. The stored file can't run code or load anything.
- **Cap heavy effects.** Filters stay allowed for the look, but blur and morphology radii, turbulence octaves, primitives per filter, filter regions and the number of filtered elements are clamped, `<use>` of an element that itself contains `<use>` is dropped (exponential expansion), and an image over 8,000 elements is rejected. A bad reply can look plainer, but can't hang the tab.
- **Shown as an image.** The viewer and the note card render it with `<img>` from a blob URL; SVG in an `<img>` never runs scripts or loads subresources. The file is served with `Content-Security-Policy: sandbox; default-src 'none'; style-src 'unsafe-inline'; img-src data:; font-src data:` in case it is opened directly.
- **Downloadable** as SVG or as PNG (2x, drawn onto a canvas in the browser). Because the SVG has no external references, the canvas is never tainted.
- **No migration.** A note is an infographic when its attachment MIME type is `image/svg+xml`. SVG is not in the upload allow-list (`ALLOWED_TYPES`), so only the generator creates such notes. This also avoids clashing with migration 105 claimed by the open meeting-notes PR.
- Jobs reuse the explainer job tracking, now shared in `api/generation_jobs.py`.

## Alternatives considered
- **Raster image model** (e.g. gpt-image) with baoyu's prompts as written: closest to baoyu's look, but needs a new model type, settings UI and per-image cost, and image models often garble text.
- **HTML page like explainers:** richest layout, but PNG export from inside the locked sandbox is impractical and an HTML download would run outside it.

## Consequences
- Styles that only work as raster art (claymation, LEGO, watercolour, knolling, origami) are left out.
- SVG text does not wrap, so layout quality depends on the model breaking lines itself; weaker models produce stiffer posters. The prompt spells out line lengths and font sizes.
- Posters use system fonts, so the PNG looks slightly different from one machine to another.
