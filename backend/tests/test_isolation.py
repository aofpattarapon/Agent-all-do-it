"""Unit tests for the project-isolation SQL guard (app.core.project_isolation).

Pure-logic tests — no database required.
"""

import pytest

from app.core.project_isolation import (
    QueryIsolationError,
    build_scoped_query,
    extract_project_id_from_path,
    validate_raw_query,
)

PID = "11111111-1111-1111-1111-111111111111"
OTHER = "22222222-2222-2222-2222-222222222222"


# ── validate_raw_query: rejections ──────────────────────────────────────────

@pytest.mark.parametrize(
    "sql",
    [
        "UPDATE knowledge_documents SET content='x'",          # not select
        "DELETE FROM runs",                                     # not select
        "SELECT 1; DROP TABLE users",                           # stacked
        "SELECT * FROM runs -- WHERE project_id='x'",           # comment smuggle
        "SELECT * FROM runs /* x */ WHERE 1=1",                 # block comment
        "SELECT * FROM users WHERE id='x'",                     # default-deny table
        "SELECT * FROM conversations",                          # default-deny table
        "SELECT * FROM runs",                                   # scoped, no predicate
        "SELECT pg_sleep(10)",                                  # forbidden fn (and no table)
    ],
)
def test_raw_query_rejected(sql):
    with pytest.raises(QueryIsolationError):
        validate_raw_query(sql, PID)


def test_raw_query_rejects_other_projects_id():
    sql = f"SELECT * FROM runs WHERE project_id = '{OTHER}'"
    with pytest.raises(QueryIsolationError):
        validate_raw_query(sql, PID)


def test_raw_query_rejects_tautology_bypass():
    sql = f"SELECT * FROM runs WHERE project_id = '{PID}' OR 1=1"
    with pytest.raises(QueryIsolationError):
        validate_raw_query(sql, PID)


def test_raw_query_rejects_into_outfile():
    sql = "SELECT * INTO new_table FROM agent_templates"
    with pytest.raises(QueryIsolationError):
        validate_raw_query(sql, PID)


# ── validate_raw_query: acceptances ─────────────────────────────────────────

def test_raw_query_allows_global_catalog_unscoped():
    sql = "SELECT id, name FROM agent_templates"
    assert validate_raw_query(sql, PID) == sql


def test_raw_query_allows_correctly_scoped():
    sql = f"SELECT title FROM knowledge_documents WHERE project_id = '{PID}'"
    assert validate_raw_query(sql, PID) == sql


def test_raw_query_allows_bind_parameter_form():
    sql = "SELECT title FROM knowledge_documents WHERE project_id = :project_id"
    assert validate_raw_query(sql, PID) == sql


def test_raw_query_allows_aliased_predicate_and_strips_semicolon():
    sql = f"SELECT r.id FROM runs r WHERE r.project_id = '{PID}'"
    assert validate_raw_query(sql + ";", PID) == sql


def test_raw_query_projects_table_filtered_by_id():
    ok = f"SELECT name FROM projects WHERE id = '{PID}'"
    assert validate_raw_query(ok, PID) == ok
    with pytest.raises(QueryIsolationError):
        validate_raw_query("SELECT name FROM projects", PID)


# ── build_scoped_query ──────────────────────────────────────────────────────

def test_build_scoped_query_forces_project_filter():
    sql, params = build_scoped_query(PID, "knowledge_documents")
    assert "WHERE project_id = :project_id" in sql
    assert params["project_id"] == PID
    assert sql.endswith("LIMIT 50")


def test_build_scoped_query_binds_filter_values():
    sql, params = build_scoped_query(
        PID, "runs", columns=["id", "status"], filters={"status": "completed"}, limit=10
    )
    assert "SELECT id, status FROM runs" in sql
    assert "project_id = :project_id" in sql
    assert "status = :f_0" in sql
    assert params == {"project_id": PID, "f_0": "completed"}
    assert sql.endswith("LIMIT 10")


def test_build_scoped_query_clamps_limit():
    sql, _ = build_scoped_query(PID, "runs", limit=10_000)
    assert sql.endswith("LIMIT 100")


def test_build_scoped_query_rejects_bad_identifiers():
    with pytest.raises(QueryIsolationError):
        build_scoped_query(PID, "runs", columns=["id; DROP TABLE x"])
    with pytest.raises(QueryIsolationError):
        build_scoped_query(PID, "runs", filters={"1=1 OR": "x"})


def test_build_scoped_query_rejects_non_scoped_table():
    with pytest.raises(QueryIsolationError):
        build_scoped_query(PID, "agent_templates")
    with pytest.raises(QueryIsolationError):
        build_scoped_query(PID, "users")


# ── path extraction ─────────────────────────────────────────────────────────

def test_extract_project_id_from_path():
    assert extract_project_id_from_path(f"/api/v1/projects/{PID}/runs") == PID
    assert extract_project_id_from_path(f"/api/v1/projects/{PID}") == PID
    assert extract_project_id_from_path("/api/v1/projects") is None
    assert extract_project_id_from_path("/api/v1/health") is None
