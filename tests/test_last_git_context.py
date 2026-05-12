"""Tests for `pomo start --last` git-context restoration and `pomo last-session` command."""
import json
from typer.testing import CliRunner

from pomocli.cli.main import app
from pomocli.db.operations import (
    create_session,
    get_or_create_task,
    get_recent_sessions,
)
from pomocli.db.connection import init_db

runner = CliRunner()


def _seed_session(task_name: str, project: str | None, repo: str | None, branch: str | None) -> int:
    task_id = get_or_create_task(task_name, project)
    return create_session(task_id, repo, branch)


def _patch_db(mocker, tmp_path):
    db_path = tmp_path / "test.db"
    mocker.patch("pomocli.db.connection.DB_PATH", db_path)
    mocker.patch("pomocli.cli.main.DB_PATH", db_path)
    init_db()


def test_get_recent_sessions_exposes_git_columns(mocker, tmp_path):
    _patch_db(mocker, tmp_path)
    _seed_session("write code", "pomocli", "pomocli", "main")

    rows = get_recent_sessions(limit=1)
    assert len(rows) == 1
    assert rows[0]["git_repo"] == "pomocli"
    assert rows[0]["git_branch"] == "main"


def test_last_session_cmd_json(mocker, tmp_path):
    _patch_db(mocker, tmp_path)
    _seed_session("review pr", "pomocli", "pomocli", "feature/x")

    result = runner.invoke(app, ["last-session", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout.strip())
    assert payload == {
        "task": "review pr",
        "project": "pomocli",
        "git_repo": "pomocli",
        "git_branch": "feature/x",
    }


def test_last_session_cmd_json_empty(mocker, tmp_path):
    _patch_db(mocker, tmp_path)
    result = runner.invoke(app, ["last-session", "--json"])
    assert result.exit_code == 0
    assert json.loads(result.stdout.strip()) == {}


def test_last_restores_git_when_cwd_is_not_git(mocker, tmp_path):
    _patch_db(mocker, tmp_path)
    _seed_session("debug daemon", "pomocli", "pomocli", "main")

    # cwd is not a git repo
    mocker.patch("pomocli.cli.main.get_git_context", return_value=(None, None))
    mocker.patch("pomocli.cli.main.ensure_daemon")
    mocker.patch(
        "pomocli.daemon.client.DaemonClient.status",
        return_value={"status": "ok", "data": {"state": "idle", "db_path": "x"}},
    )
    mocker.patch("pomocli.cli.main._require_daemon_db_matches_cli")
    mocker.patch(
        "pomocli.daemon.client.DaemonClient.start",
        return_value={"status": "ok"},
    )
    captured = {}
    real_create = create_session

    def spy_create(task_id, repo, branch, timer_mode="countdown"):
        captured["repo"] = repo
        captured["branch"] = branch
        return real_create(task_id, repo, branch, timer_mode=timer_mode)

    mocker.patch("pomocli.cli.main.create_session", side_effect=spy_create)

    result = runner.invoke(app, ["start", "--last"])
    assert result.exit_code == 0, result.stdout
    assert captured["repo"] == "pomocli"
    assert captured["branch"] == "main"


def test_last_does_not_override_when_cwd_is_git(mocker, tmp_path):
    _patch_db(mocker, tmp_path)
    _seed_session("debug daemon", "pomocli", "old-repo", "old-branch")

    # cwd IS a git repo — live detection wins
    mocker.patch(
        "pomocli.cli.main.get_git_context", return_value=("live-repo", "live-branch")
    )
    mocker.patch("pomocli.cli.main.ensure_daemon")
    mocker.patch(
        "pomocli.daemon.client.DaemonClient.status",
        return_value={"status": "ok", "data": {"state": "idle", "db_path": "x"}},
    )
    mocker.patch("pomocli.cli.main._require_daemon_db_matches_cli")
    mocker.patch(
        "pomocli.daemon.client.DaemonClient.start",
        return_value={"status": "ok"},
    )
    captured = {}
    real_create = create_session

    def spy_create(task_id, repo, branch, timer_mode="countdown"):
        captured["repo"] = repo
        captured["branch"] = branch
        return real_create(task_id, repo, branch, timer_mode=timer_mode)

    mocker.patch("pomocli.cli.main.create_session", side_effect=spy_create)

    result = runner.invoke(app, ["start", "--last"])
    assert result.exit_code == 0, result.stdout
    assert captured["repo"] == "live-repo"
    assert captured["branch"] == "live-branch"
