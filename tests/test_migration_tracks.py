"""Two migration tracks: upstream (_sbl_migrations) and Nova-Notes fork (_nova_migrations)."""

from unittest.mock import AsyncMock, patch

import pytest

from open_notebook.database import async_migrate as am


def test_tracks_are_registered_with_matching_down_files():
    m = am.AsyncMigrationManager()
    assert len(m.up_migrations) == len(m.down_migrations) == 25
    assert len(m.nova_runner.up_migrations) == len(m.nova_runner.down_migrations) == 5
    assert (m.nova_runner.table, m.nova_runner.base) == (am.NOVA_TABLE, am.NOVA_BASE)
    # 101 = notebook folders (was upstream-track 27 before the split)
    assert "folder" in m.nova_runner.up_migrations[1].sql
    # 104 = generated explainer flag on notes
    assert "explainer" in m.nova_runner.up_migrations[4].sql


def _versions(sbl, nova):
    async def fake(table=am.UPSTREAM_TABLE):
        rows = sbl if table == am.UPSTREAM_TABLE else nova
        return [{"version": v} for v in rows]

    return fake


@pytest.mark.asyncio
async def test_legacy_fork_records_move_in_one_transaction():
    m = am.AsyncMigrationManager()
    with (
        patch.object(am, "get_all_versions", new=_versions(range(1, 30), [])),
        patch.object(am, "repo_query", new=AsyncMock()) as q,
    ):
        await m.adopt_legacy_fork_versions()
    q.assert_awaited_once()
    assert q.await_args is not None
    sql = q.await_args.args[0]
    assert sql.startswith("BEGIN TRANSACTION;") and sql.endswith("COMMIT TRANSACTION;")
    for old, new in [(26, 100), (27, 101), (28, 102), (29, 103)]:
        assert f"'_nova_migrations', {new})" in sql and f"moved_from = {old}" in sql
        assert f"DELETE type::thing('_sbl_migrations', {old});" in sql
    assert "'_sbl_migrations', 25)" not in sql


@pytest.mark.asyncio
async def test_no_move_once_fork_track_exists():
    # After the split, an upstream 26 must stay on the upstream track.
    m = am.AsyncMigrationManager()
    with (
        patch.object(am, "get_all_versions", new=_versions(range(1, 27), [100])),
        patch.object(am, "repo_query", new=AsyncMock()) as q,
    ):
        await m.adopt_legacy_fork_versions()
    q.assert_not_awaited()


@pytest.mark.asyncio
async def test_needs_migration_when_only_the_record_move_is_pending():
    m = am.AsyncMigrationManager()
    with patch.object(am, "get_all_versions", new=_versions(range(1, 30), [])):
        assert await m.needs_migration() is True


@pytest.mark.asyncio
async def test_up_to_date_on_both_tracks():
    m = am.AsyncMigrationManager()
    with patch.object(
        am, "get_all_versions", new=_versions(range(1, 26), [100, 101, 102, 103, 104])
    ):
        assert await m.needs_migration() is False
