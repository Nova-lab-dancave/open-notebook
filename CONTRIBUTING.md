# Contributing to Nova-Notes

Nova-Notes is a fork of [lfnovo/open-notebook](https://github.com/lfnovo/open-notebook) with extra features (sections and folders, notebook podcasts, Read a Script, file drops, discovery). This page covers how **this fork** works. For the code itself (architecture, conventions, recipes), the upstream developer docs in [docs/7-DEVELOPMENT/](docs/7-DEVELOPMENT/index.md) and the `AGENTS.md` files still apply. Where they disagree with this page, this page wins.

## How work flows

1. **Pick or open an Issue** in this repo and assign yourself, so two people don't build the same thing. Small obvious fixes (typos, docs, a one-line bug) can skip this.
2. **Branch from `main`**: `<your-github-name>/<short-topic>`, e.g. `adrian/podcast-chapters`. Never push to `main`; it is protected.
3. **Commit with [Conventional Commits](https://www.conventionalcommits.org/)**: `feat(podcasts): …`, `fix(notes): …`, `docs: …`. The PR title uses the same format.
4. **Open a PR against `heli-konton/open-notebook` `main`.** Not against lfnovo: `gh pr create` picks the upstream repo by default in a fork, so run `gh repo set-default heli-konton/open-notebook` once in your clone (or pass `--repo heli-konton/open-notebook`).
5. **CI must pass and one code owner must approve** (see [.github/CODEOWNERS](.github/CODEOWNERS)). PRs are squash-merged and the branch is deleted.

## What happens after a merge

- Every merge to `main` builds, smoke-tests and publishes a Docker image `ghcr.io/heli-konton/open-notebook:v1.15.0-nova.<run>` (workflow `nova-custom.yml`).
- **Publishing is not deploying.** The running instance only changes when the maintainer deploys a specific image by hand. Merging can't break anyone's live data.

## Before you open a PR

Run the same checks as CI:

```bash
uv run ruff check . && uv run ruff format --check . && uv run python -m mypy . && uv run pytest tests
cd frontend && npm run lint && npm run test && npm run build
```

- **CHANGELOG:** every user-visible change adds a line under `## [Unreleased]` in the right section (`### Added`, `### Changed`, `### Fixed`, …). Never add a second section of the same type.
- **UI text:** every string goes through `t('…')` and the key is added to **all 14** locale files in `frontend/src/lib/locales/` (English text is fine in non-English files).
- **Tests:** new behaviour comes with tests. Bugs get a test that fails before the fix.

## Local setup

See [Development Setup](docs/7-DEVELOPMENT/development-setup.md). In short: `uv sync`, `cd frontend && npm install`, a `.env` with `SURREAL_URL=ws://localhost:8000/rpc` and any `OPEN_NOTEBOOK_ENCRYPTION_KEY`, then `make start-all`. Use your own AI provider keys locally; never commit keys or `.env`.

## Database migrations: the fork has its own track

Schema changes made in this fork are **Nova-Notes migrations, numbered from 100**, recorded in the `_nova_migrations` table. Upstream's migrations stay `1, 2, 3, …` in `_sbl_migrations`. Keeping them apart means upstream can add its own `26` without clashing with ours ([ADR-014](docs/7-DEVELOPMENT/decisions/ADR-014-fork-migration-track.md)).

To add one:

1. Create `open_notebook/database/migrations/<next>.surrealql` and `<next>_down.surrealql`, where `<next>` is one more than the highest file at or above 100.
2. Append that number to `NOVA_MIGRATION_NUMBERS` in `open_notebook/database/async_migrate.py`.
3. Never renumber or edit a migration once it is on `main`. Fix forward with a new one.
4. Test against a database that already has data, not only an empty one.

Never add files numbered below 100: those belong to upstream and arrive when we sync.

## Syncing with upstream

This fork is maintained independently: the in-app "update available" notice follows this repo, not lfnovo. Every Monday the `upstream-watch` workflow opens an Issue when lfnovo publishes a newer release. The maintainer reviews it and merges `lfnovo/open-notebook` `main` into the fork on a branch (`git fetch upstream --tags && git merge upstream/main`, then a normal PR); security releases go first. Don't send fork features to lfnovo from this repo. If something is worth upstreaming, raise it with the maintainer first.

## Security

- Don't commit secrets, `.env` files, real API keys or personal data. CI has no secrets: images publish with the built-in `GITHUB_TOKEN`.
- Changes to `.github/workflows/` and migrations always need a code-owner review.
- Report security problems privately to the maintainer, not in a public Issue.
