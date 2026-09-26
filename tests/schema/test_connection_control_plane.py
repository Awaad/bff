from __future__ import annotations

from collections.abc import Mapping, Sequence

from tests.support.database import IDS, DatabaseTestEnvironment


def _index_names(value: object) -> set[str]:
    names: set[str] = set()
    if isinstance(value, Mapping):
        index_name = value.get("Index Name")
        if isinstance(index_name, str):
            names.add(index_name)
        for child in value.values():
            names.update(_index_names(child))
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        for child in value:
            names.update(_index_names(child))
    return names


def test_connection_pagination_index_matches_accepted_order(
    postgres_test_db: DatabaseTestEnvironment,
) -> None:
    with postgres_test_db.owner_connection() as connection:
        index_definition = connection.execute(
            """
            SELECT indexdef
            FROM pg_indexes
            WHERE schemaname = 'app'
              AND tablename = 'connections'
              AND indexname = 'idx_connections_workspace_created_id'
            """
        ).fetchone()

    assert index_definition is not None
    raw_definition = index_definition[0]
    assert isinstance(raw_definition, str)
    normalized = " ".join(raw_definition.split())
    assert "(workspace_id, created_at DESC, id DESC)" in normalized


def test_connection_page_query_can_use_pagination_index(
    postgres_test_db: DatabaseTestEnvironment,
) -> None:
    with postgres_test_db.owner_connection() as connection:
        connection.execute("SET enable_seqscan = off")
        explained = connection.execute(
            """
            EXPLAIN (FORMAT JSON)
            SELECT id, workspace_id, name, provider_key, access_mode, status,
                   created_at, updated_at, archived_at
            FROM app.connections
            WHERE workspace_id = %s
            ORDER BY created_at DESC, id DESC
            LIMIT 51
            """,
            (IDS["workspace_1"],),
        ).fetchone()

    assert explained is not None
    assert "idx_connections_workspace_created_id" in _index_names(explained[0])
