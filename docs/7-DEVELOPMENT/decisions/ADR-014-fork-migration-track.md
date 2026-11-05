# ADR-014: Fork migrations get their own track

**Status:** Accepted (Nova-Notes fork, 2026-11)

## Context

Migrations are positional: `_sbl_migrations` stores how many files in `AsyncMigrationManager.up_migrations` have run, and the next run starts at that index. The Nova-Notes fork added its own migrations after upstream's last one (26-29 on top of upstream's 25). As soon as upstream adds its own migration 26, a fork database that already recorded "version 29" would skip upstream's new files, or a merged list would run the wrong file at the wrong position.

## Decision

Two independent tracks run at startup, upstream first:

| Track | Files | Recorded in | Version stored |
|---|---|---|---|
| Upstream | `1 … N` | `_sbl_migrations` | `1 … N` |
| Nova-Notes fork | `100, 101, …` (`NOVA_MIGRATION_NUMBERS`) | `_nova_migrations` | the file number |

The former fork migrations 26-29 were renamed to 100-103 with unchanged SQL. A one-time handover (`adopt_legacy_fork_versions`) runs while `_nova_migrations` is empty: it moves any `_sbl_migrations` records numbered 26 or higher to `_nova_migrations` (26→100 … 29→103, keeping `moved_from`) in a single transaction, so nothing is re-run. Once the fork track has a record, the handover never runs again, so a later upstream 26 stays on the upstream track.

## Consequences

- Upstream merges no longer need migration renumbering.
- Fork migrations always run after all upstream ones. A fork migration that depends on an upstream schema change works; one that upstream would have to depend on is not possible (upstream doesn't know about the fork).
- Rolling an existing database back to an image from before this change is not supported without restoring a backup: the older image would see `_sbl_migrations` at 25 and re-run the fork files from position 26.
- Verified against a real SurrealDB: fresh database, a database migrated to 29 by the old code, a database at 26 from an earlier fork image, a restart (no-op), and a simulated upstream migration 26 added after the split. Schemas of the fresh and handed-over databases were identical.
