"""
Async migration system for SurrealDB using the official Python client.
Based on patterns from sblpy migration system.
"""

from typing import List

from loguru import logger

from .repository import db_connection, repo_query

# Two migration tracks, so the fork never collides with upstream numbering:
# - upstream (lfnovo) migrations 1..N, recorded in _sbl_migrations;
# - Nova-Notes fork migrations numbered from 100, recorded in _nova_migrations.
# Upstream can add its own 26, 27, ... without clashing with fork schema.
UPSTREAM_TABLE = "_sbl_migrations"
NOVA_TABLE = "_nova_migrations"
NOVA_BASE = 99  # fork migration k (1-based) is file/version NOVA_BASE + k
NOVA_MIGRATION_NUMBERS = [100, 101, 102, 103, 104, 105, 106]

# Before the split, the fork's migrations were upstream-track versions 26-29
# (now files 100-103). Databases from that time get those records moved once.
LEGACY_FORK_FIRST_VERSION = 26


class AsyncMigration:
    """
    Handles individual migration operations with async support.
    """

    def __init__(self, sql: str) -> None:
        """Initialize migration with SQL content."""
        self.sql = sql

    @classmethod
    def from_file(cls, file_path: str) -> "AsyncMigration":
        """Create migration from SQL file."""
        with open(file_path, "r", encoding="utf-8") as file:
            raw_content = file.read()
            # Clean up SQL content
            lines = []
            for line in raw_content.split("\n"):
                line = line.strip()
                if line and not line.startswith("--"):
                    lines.append(line)
            sql = " ".join(lines)
            return cls(sql)

    async def run(
        self, bump: bool = True, table: str = UPSTREAM_TABLE, base: int = 0
    ) -> None:
        """Run the migration."""
        try:
            async with db_connection() as connection:
                await connection.query(self.sql)

            if bump:
                await bump_version(table, base)
            else:
                await lower_version(table, base)

        except Exception as e:
            logger.error(f"Migration failed: {str(e)}")
            raise


class AsyncMigrationRunner:
    """
    Handles running multiple migrations in sequence.
    """

    def __init__(
        self,
        up_migrations: List[AsyncMigration],
        down_migrations: List[AsyncMigration],
        table: str = UPSTREAM_TABLE,
        base: int = 0,
    ) -> None:
        """Initialize runner with migration lists for one track."""
        self.up_migrations = up_migrations
        self.down_migrations = down_migrations
        self.table = table
        self.base = base

    async def applied_count(self) -> int:
        """How many of this track's migrations are applied."""
        return await get_latest_version(self.table, self.base) - self.base

    async def needs_migration(self) -> bool:
        return await self.applied_count() < len(self.up_migrations)

    async def run_all(self) -> None:
        """Run all pending up migrations."""
        for i in range(await self.applied_count(), len(self.up_migrations)):
            logger.info(f"Running migration {self.base + i + 1}")
            await self.up_migrations[i].run(True, self.table, self.base)

    async def run_one_up(self) -> None:
        """Run one up migration."""
        done = await self.applied_count()
        if done < len(self.up_migrations):
            logger.info(f"Running migration {self.base + done + 1}")
            await self.up_migrations[done].run(True, self.table, self.base)

    async def run_one_down(self) -> None:
        """Run one down migration."""
        done = await self.applied_count()
        if done > 0:
            logger.info(f"Rolling back migration {self.base + done}")
            await self.down_migrations[done - 1].run(False, self.table, self.base)


class AsyncMigrationManager:
    """
    Main migration manager with async support.
    """

    def __init__(self):
        """Initialize migration manager."""
        self.up_migrations = [
            AsyncMigration.from_file("open_notebook/database/migrations/1.surrealql"),
            AsyncMigration.from_file("open_notebook/database/migrations/2.surrealql"),
            AsyncMigration.from_file("open_notebook/database/migrations/3.surrealql"),
            AsyncMigration.from_file("open_notebook/database/migrations/4.surrealql"),
            AsyncMigration.from_file("open_notebook/database/migrations/5.surrealql"),
            AsyncMigration.from_file("open_notebook/database/migrations/6.surrealql"),
            AsyncMigration.from_file("open_notebook/database/migrations/7.surrealql"),
            AsyncMigration.from_file("open_notebook/database/migrations/8.surrealql"),
            AsyncMigration.from_file("open_notebook/database/migrations/9.surrealql"),
            AsyncMigration.from_file("open_notebook/database/migrations/10.surrealql"),
            AsyncMigration.from_file("open_notebook/database/migrations/11.surrealql"),
            AsyncMigration.from_file("open_notebook/database/migrations/12.surrealql"),
            AsyncMigration.from_file("open_notebook/database/migrations/13.surrealql"),
            AsyncMigration.from_file("open_notebook/database/migrations/14.surrealql"),
            AsyncMigration.from_file("open_notebook/database/migrations/15.surrealql"),
            AsyncMigration.from_file("open_notebook/database/migrations/16.surrealql"),
            AsyncMigration.from_file("open_notebook/database/migrations/17.surrealql"),
            AsyncMigration.from_file("open_notebook/database/migrations/18.surrealql"),
            AsyncMigration.from_file("open_notebook/database/migrations/19.surrealql"),
            AsyncMigration.from_file("open_notebook/database/migrations/20.surrealql"),
            AsyncMigration.from_file("open_notebook/database/migrations/21.surrealql"),
            AsyncMigration.from_file("open_notebook/database/migrations/22.surrealql"),
            AsyncMigration.from_file("open_notebook/database/migrations/23.surrealql"),
            AsyncMigration.from_file("open_notebook/database/migrations/24.surrealql"),
            AsyncMigration.from_file("open_notebook/database/migrations/25.surrealql"),
        ]
        self.down_migrations = [
            AsyncMigration.from_file(
                "open_notebook/database/migrations/1_down.surrealql"
            ),
            AsyncMigration.from_file(
                "open_notebook/database/migrations/2_down.surrealql"
            ),
            AsyncMigration.from_file(
                "open_notebook/database/migrations/3_down.surrealql"
            ),
            AsyncMigration.from_file(
                "open_notebook/database/migrations/4_down.surrealql"
            ),
            AsyncMigration.from_file(
                "open_notebook/database/migrations/5_down.surrealql"
            ),
            AsyncMigration.from_file(
                "open_notebook/database/migrations/6_down.surrealql"
            ),
            AsyncMigration.from_file(
                "open_notebook/database/migrations/7_down.surrealql"
            ),
            AsyncMigration.from_file(
                "open_notebook/database/migrations/8_down.surrealql"
            ),
            AsyncMigration.from_file(
                "open_notebook/database/migrations/9_down.surrealql"
            ),
            AsyncMigration.from_file(
                "open_notebook/database/migrations/10_down.surrealql"
            ),
            AsyncMigration.from_file(
                "open_notebook/database/migrations/11_down.surrealql"
            ),
            AsyncMigration.from_file(
                "open_notebook/database/migrations/12_down.surrealql"
            ),
            AsyncMigration.from_file(
                "open_notebook/database/migrations/13_down.surrealql"
            ),
            AsyncMigration.from_file(
                "open_notebook/database/migrations/14_down.surrealql"
            ),
            AsyncMigration.from_file(
                "open_notebook/database/migrations/15_down.surrealql"
            ),
            AsyncMigration.from_file(
                "open_notebook/database/migrations/16_down.surrealql"
            ),
            AsyncMigration.from_file(
                "open_notebook/database/migrations/17_down.surrealql"
            ),
            AsyncMigration.from_file(
                "open_notebook/database/migrations/18_down.surrealql"
            ),
            AsyncMigration.from_file(
                "open_notebook/database/migrations/19_down.surrealql"
            ),
            AsyncMigration.from_file(
                "open_notebook/database/migrations/20_down.surrealql"
            ),
            AsyncMigration.from_file(
                "open_notebook/database/migrations/21_down.surrealql"
            ),
            AsyncMigration.from_file(
                "open_notebook/database/migrations/22_down.surrealql"
            ),
            AsyncMigration.from_file(
                "open_notebook/database/migrations/23_down.surrealql"
            ),
            AsyncMigration.from_file(
                "open_notebook/database/migrations/24_down.surrealql"
            ),
            AsyncMigration.from_file(
                "open_notebook/database/migrations/25_down.surrealql"
            ),
        ]
        self.runner = AsyncMigrationRunner(
            up_migrations=self.up_migrations,
            down_migrations=self.down_migrations,
        )
        folder = "open_notebook/database/migrations"
        self.nova_runner = AsyncMigrationRunner(
            up_migrations=[
                AsyncMigration.from_file(f"{folder}/{n}.surrealql")
                for n in NOVA_MIGRATION_NUMBERS
            ],
            down_migrations=[
                AsyncMigration.from_file(f"{folder}/{n}_down.surrealql")
                for n in NOVA_MIGRATION_NUMBERS
            ],
            table=NOVA_TABLE,
            base=NOVA_BASE,
        )

    async def get_current_version(self) -> int:
        """Get current upstream-track database version."""
        return await get_latest_version()

    async def get_nova_version(self) -> int:
        """Get current fork-track version (NOVA_BASE when none applied)."""
        return await get_latest_version(NOVA_TABLE, NOVA_BASE)

    async def adopt_legacy_fork_versions(self) -> None:
        """Move pre-split fork records (upstream versions 26+) to the fork track.

        Runs only while the fork track is empty, so a later upstream 26 is
        never mistaken for a fork migration. One transaction: all or nothing.
        """
        if await get_all_versions(NOVA_TABLE):
            return
        legacy = [
            v["version"]
            for v in await get_all_versions(UPSTREAM_TABLE)
            if v["version"] >= LEGACY_FORK_FIRST_VERSION
        ]
        if not legacy:
            return
        offset = NOVA_MIGRATION_NUMBERS[0] - LEGACY_FORK_FIRST_VERSION
        statements = ["BEGIN TRANSACTION;"]
        for old in sorted(legacy):
            statements.append(
                f"CREATE type::thing('{NOVA_TABLE}', {old + offset}) "
                f"SET version = {old + offset}, applied_at = time::now(), "
                f"moved_from = {old};"
            )
            statements.append(f"DELETE type::thing('{UPSTREAM_TABLE}', {old});")
        statements.append("COMMIT TRANSACTION;")
        await repo_query(" ".join(statements))
        logger.info(
            f"Moved fork migration records {sorted(legacy)} from "
            f"{UPSTREAM_TABLE} to {NOVA_TABLE} as {[v + offset for v in sorted(legacy)]}"
        )

    async def ping(self) -> None:
        """Check whether SurrealDB is reachable for migration startup."""
        async with db_connection() as connection:
            await connection.query("RETURN true;")

        # Also exercise the migration version path. get_current_version() already
        # treats a missing migrations table as version 0 for fresh databases.
        await self.get_current_version()

    async def needs_migration(self) -> bool:
        """Check if either track (or the one-time record move) is pending."""
        legacy = [
            v
            for v in await get_all_versions(UPSTREAM_TABLE)
            if v["version"] >= LEGACY_FORK_FIRST_VERSION
        ]
        if legacy and not await get_all_versions(NOVA_TABLE):
            return True
        return (
            await self.runner.needs_migration()
            or await self.nova_runner.needs_migration()
        )

    async def run_migration_up(self):
        """Run all pending migrations: upstream track first, then the fork's."""
        current_version = await self.get_current_version()
        logger.info(f"Current version before migration: {current_version}")

        if await self.needs_migration():
            try:
                await self.adopt_legacy_fork_versions()
                await self.runner.run_all()
                await self.nova_runner.run_all()
                new_version = await self.get_current_version()
                logger.info(
                    f"Migration successful. New version: {new_version}, "
                    f"Nova-Notes version: {await self.get_nova_version()}"
                )
            except Exception as e:
                logger.error(f"Migration failed: {str(e)}")
                raise
        else:
            logger.info("Database is already at the latest version")


# Database version management functions
async def get_latest_version(table: str = UPSTREAM_TABLE, base: int = 0) -> int:
    """Get the latest version from a migrations table (``base`` when empty)."""
    try:
        versions = await get_all_versions(table)
        if not versions:
            return base
        return max(version["version"] for version in versions)
    except Exception:
        # If migrations table doesn't exist, nothing is applied
        return base


async def get_all_versions(table: str = UPSTREAM_TABLE) -> List[dict]:
    """Get all versions from a migrations table."""
    try:
        result = await repo_query(
            "SELECT * FROM type::table($table) ORDER BY version;", {"table": table}
        )
        if not isinstance(result, list):
            return []
        return result
    except Exception:
        # If table doesn't exist, return empty list
        return []


async def bump_version(table: str = UPSTREAM_TABLE, base: int = 0) -> None:
    """Bump the version by adding a new entry to a migrations table."""
    current_version = await get_latest_version(table, base)
    new_version = current_version + 1

    await repo_query(
        "CREATE type::thing($table, $version) SET version = $version, applied_at = time::now();",
        {"table": table, "version": new_version},
    )


async def lower_version(table: str = UPSTREAM_TABLE, base: int = 0) -> None:
    """Lower the version by removing the latest entry from a migrations table."""
    current_version = await get_latest_version(table, base)
    if current_version > base:
        await repo_query(
            "DELETE type::thing($table, $version);",
            {"table": table, "version": current_version},
        )
