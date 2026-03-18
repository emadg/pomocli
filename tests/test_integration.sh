#!/usr/bin/env bash
#
# Integration test for pomocli — starts the daemon and exercises every CLI command.
# Run: ./tests/test_integration.sh
#
set -euo pipefail

PASS=0
FAIL=0
SOCKET="$HOME/.config/pomocli/pomo.sock"

# ── Helpers ───────────────────────────────────────────────────────

cleanup() {
    pkill -f "pomocli.daemon" 2>/dev/null || true
    rm -f "$SOCKET" "$HOME/.config/pomocli/pomo.pid"
}

assert_contains() {
    local label="$1" output="$2" expected="$3"
    if echo "$output" | grep -qF "$expected"; then
        echo "  PASS: $label"
        PASS=$((PASS + 1))
    else
        echo "  FAIL: $label — expected '$expected' in output:"
        echo "        $output"
        FAIL=$((FAIL + 1))
    fi
}

assert_not_contains() {
    local label="$1" output="$2" unexpected="$3"
    if echo "$output" | grep -qF "$unexpected"; then
        echo "  FAIL: $label — did NOT expect '$unexpected' in output:"
        echo "        $output"
        FAIL=$((FAIL + 1))
    else
        echo "  PASS: $label"
        PASS=$((PASS + 1))
    fi
}

# ── Setup ─────────────────────────────────────────────────────────

trap cleanup EXIT
cleanup

echo "==> Initializing database"
out=$(uv run pomo init 2>&1)
assert_contains "init succeeds" "$out" "Database initialized"

echo ""
echo "==> Starting daemon"
uv run python -m pomocli.daemon &>/dev/null &
DAEMON_PID=$!
# Wait for socket to appear (up to 5s)
for i in $(seq 1 10); do
    [ -S "$SOCKET" ] && break
    sleep 0.5
done
if [ ! -S "$SOCKET" ]; then
    echo "  FAIL: Daemon did not create socket within 5s"
    exit 1
fi
echo "  Daemon running (PID $DAEMON_PID)"

# ── Tests ─────────────────────────────────────────────────────────

echo ""
echo "==> Test: status (no session)"
out=$(uv run pomo status 2>&1)
assert_contains "shows not running" "$out" "Not running"
assert_not_contains "no daemon-down message" "$out" "Daemon down"

echo ""
echo "==> Test: start a session"
out=$(uv run pomo start "Integration Test" -d 1 -p "CI" -t focus -t deep 2>&1)
assert_contains "start confirms task" "$out" "Started session for 'Integration Test'"
assert_contains "start shows project" "$out" "Project: CI"
assert_contains "start shows tags" "$out" "Tags: focus, deep"

echo ""
echo "==> Test: status (running)"
sleep 1
out=$(uv run pomo status 2>&1)
assert_contains "status shows running" "$out" "Running"
assert_contains "status shows time" "$out" "left"

echo ""
echo "==> Test: double start blocked"
out=$(uv run pomo start "Another Task" -d 1 2>&1 || true)
assert_contains "rejects double start" "$out" "already running"

echo ""
echo "==> Test: distract (with description)"
out=$(uv run pomo distract "Checked Slack" 2>&1)
assert_contains "distract logged" "$out" "Distraction logged: Checked Slack"

echo ""
echo "==> Test: distract (no description)"
out=$(uv run pomo distract 2>&1)
assert_contains "distract logged bare" "$out" "Distraction logged"

echo ""
echo "==> Test: pause"
out=$(uv run pomo pause 2>&1)
assert_contains "pause succeeds" "$out" "Session paused"

echo ""
echo "==> Test: status (paused)"
out=$(uv run pomo status 2>&1)
assert_contains "status shows paused" "$out" "Paused"

echo ""
echo "==> Test: resume"
out=$(uv run pomo resume 2>&1)
assert_contains "resume succeeds" "$out" "Session resumed"

echo ""
echo "==> Test: stop"
out=$(uv run pomo stop 2>&1)
assert_contains "stop succeeds" "$out" "Session stopped and saved"

echo ""
echo "==> Test: status after stop"
out=$(uv run pomo status 2>&1)
assert_contains "status shows idle" "$out" "Not running"

echo ""
echo "==> Test: start --last"
out=$(uv run pomo start --last -d 1 2>&1)
assert_contains "last resumes task" "$out" "Started session for 'Integration Test'"

echo ""
echo "==> Test: kill"
out=$(uv run pomo kill 2>&1)
assert_contains "kill succeeds" "$out" "Session killed"

echo ""
echo "==> Test: report"
out=$(uv run pomo report today 2>&1)
assert_contains "report shows table" "$out" "Pomodoro Report"
assert_contains "report shows task" "$out" "Integration Test"

echo ""
echo "==> Test: help"
out=$(uv run pomo --help 2>&1)
assert_contains "help lists start" "$out" "start"
assert_contains "help lists status" "$out" "status"
assert_contains "help lists distract" "$out" "distract"
assert_contains "help lists report" "$out" "report"
assert_contains "help lists dash" "$out" "dash"

# ── Summary ───────────────────────────────────────────────────────

echo ""
echo "========================================"
echo "  Results: $PASS passed, $FAIL failed"
echo "========================================"

[ "$FAIL" -eq 0 ] && exit 0 || exit 1
