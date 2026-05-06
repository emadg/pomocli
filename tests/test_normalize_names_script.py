import importlib.util
from pathlib import Path

from pomocli.db.connection import init_db, get_connection
from pomocli.db.operations import get_or_create_task, create_session


def _load_script():
    path = Path(__file__).parent.parent / "scripts" / "normalize_names.py"
    spec = importlib.util.spec_from_file_location("normalize_names", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _bump_task_last_accessed(task_id: int, ts: str) -> None:
    conn = get_connection()
    conn.execute("UPDATE tasks SET last_accessed = ? WHERE id = ?", (ts, task_id))
    conn.commit()
    conn.close()


def _all_tasks():
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, project_name, task_name FROM tasks ORDER BY id"
    ).fetchall()
    conn.close()
    return [(r["id"], r["project_name"], r["task_name"]) for r in rows]


def _session_task_ids():
    conn = get_connection()
    rows = conn.execute("SELECT id, task_id FROM sessions ORDER BY id").fetchall()
    conn.close()
    return [(r["id"], r["task_id"]) for r in rows]


def test_dry_run_does_not_write(mocker, tmp_path, capsys):
    db_path = tmp_path / "test.db"
    mocker.patch("pomocli.db.connection.DB_PATH", db_path)
    init_db()

    get_or_create_task("the foo", "nuclear")

    script = _load_script()
    script.main(apply=False, db_path=db_path)

    # No mutation in dry-run
    assert _all_tasks() == [(1, "nuclear", "the foo")]


def test_apply_normalizes_and_merges(mocker, tmp_path):
    db_path = tmp_path / "test.db"
    mocker.patch("pomocli.db.connection.DB_PATH", db_path)
    init_db()

    older_proj = get_or_create_task("alpha", "nuclear")
    newer_proj = get_or_create_task("beta", "NuCLEAR")
    _bump_task_last_accessed(older_proj, "2024-01-01 00:00:00")
    _bump_task_last_accessed(newer_proj, "2026-01-01 00:00:00")

    # Two same-meaning task rows under same (post-normalize) project
    dup_a = get_or_create_task("the foo", "nuclear")
    dup_b = get_or_create_task("The Foo", "NuCLEAR")
    _bump_task_last_accessed(dup_a, "2024-06-01 00:00:00")
    _bump_task_last_accessed(dup_b, "2026-06-01 00:00:00")

    s_a = create_session(dup_a)
    s_b = create_session(dup_b)

    script = _load_script()
    script.main(apply=True, db_path=db_path)

    rows = _all_tasks()
    project_names = {p for _, p, _ in rows}
    # All "nuclear" variants normalized to the canonical "NuCLEAR"
    assert project_names == {"NuCLEAR"}

    # Tasks normalized; "the foo"/"The Foo" merged into one row
    foo_rows = [r for r in rows if r[2] == "The Foo"]
    assert len(foo_rows) == 1
    survivor_id = foo_rows[0][0]

    # Sessions on duplicate task rows now repointed to survivor
    sess = dict(_session_task_ids())
    assert sess[s_a] == survivor_id
    assert sess[s_b] == survivor_id


def test_normalizes_simple_lowercase_to_title(mocker, tmp_path):
    db_path = tmp_path / "test.db"
    mocker.patch("pomocli.db.connection.DB_PATH", db_path)
    init_db()

    get_or_create_task("write the docs", "my project")

    script = _load_script()
    script.main(apply=True, db_path=db_path)

    rows = _all_tasks()
    assert rows == [(1, "My Project", "Write the Docs")]
