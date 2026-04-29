"""`pomo session inspect` — session timeline, wall clock vs focus metrics."""

from __future__ import annotations

import json
from typing import Any, List, Mapping, Optional

from rich.console import Console
from rich.rule import Rule
from rich.table import Table

from ..db.operations import (
    get_session_distractions,
    get_session_events,
    get_session_listing_row,
)
from ..metrics.focus import (
    DISTRACTION_RECOVERY_CAP_SECONDS,
    attention_quality_effective_seconds,
    attention_quality_rate_value,
    distraction_recovery_charge_seconds,
    focus_block_session_score,
    pause_seconds_from_events,
    total_distraction_recovery_seconds,
)
from ..time_util import (
    format_duration_hm,
    format_duration_hms,
    format_local,
    parse_stored_utc,
    utc_now_sql,
)


def _as_dict(row: Any) -> dict[str, Any]:
    if isinstance(row, dict):
        return row
    return dict(row)


def _fmt_event_details(raw: Any) -> str:
    if raw is None:
        return "—"
    if isinstance(raw, str) and not raw.strip():
        return "—"
    try:
        if isinstance(raw, str):
            return json.dumps(json.loads(raw), separators=(",", ":"))
    except (json.JSONDecodeError, TypeError):
        pass
    return str(raw)


def _metrics_end_row(listing: Mapping[str, Any]) -> tuple[dict[str, Any], str, bool]:
    """
    Row and end_time SQL for metrics. Open sessions (no end_time) use UTC now so
    pause/recovery math matches an in-progress view.
    """
    base = _as_dict(listing)
    end_raw = base.get("end_time")
    if end_raw:
        return base, str(end_raw), False
    merged = {**base, "end_time": utc_now_sql()}
    return merged, merged["end_time"], True


def _print_one_session(session_id: int, timezone_config: str, console: Console) -> None:
    listing = get_session_listing_row(session_id)
    if listing is None:
        console.print(f"[yellow]Session id {session_id} not found; skipped.[/yellow]")
        return

    row = _as_dict(listing)
    events = get_session_events(session_id)
    distractions = get_session_distractions(session_id)
    d_ts = [str(d["timestamp"]) for d in distractions]

    public_id = row.get("public_id") or ""
    sid = int(row["id"])
    mode = str(row.get("timer_mode") or "countdown")
    status = str(row.get("status") or "?")
    task = row.get("task_name") or "—"
    project = row.get("project_name") or "—"
    dc = int(row.get("distraction_count") or 0)

    console.print(Rule(f"Session {public_id}  (id={sid})  ·  {mode}  ·  {status}"))
    console.print(f"Task: {task}  ·  Project: {project}  ·  Distractions: {dc}")

    start_sql = row.get("start_time")
    end_sql = row.get("end_time")
    start_local = format_local(str(start_sql), timezone_config) if start_sql else "—"
    if end_sql:
        end_local = format_local(str(end_sql), timezone_config)
        wall_note = ""
    else:
        end_local = "— (session open)"
        wall_note = " [dim](wall span through UTC now for metrics below)[/dim]"

    console.print("[bold]Wall clock[/bold]")
    console.print(f"  start (local):  {start_local}")
    console.print(f"  end   (local):  {end_local}{wall_note}")

    metrics_row, end_for_pause, provisional = _metrics_end_row(row)
    st_sql = str(metrics_row["start_time"])
    wall_sec: Optional[int] = None
    if start_sql and end_for_pause:
        wall_sec = int(
            max(
                0,
                (parse_stored_utc(end_for_pause) - parse_stored_utc(st_sql)).total_seconds(),
            )
        )
    if wall_sec is not None:
        console.print(
            f"  span:           {format_duration_hms(wall_sec)}   ({wall_sec}s)"
        )
    else:
        console.print("  span:           —")

    logged = int(row.get("duration_logged") or 0)
    console.print("[bold]Timer / DB[/bold]")
    console.print(
        f"  duration_logged (focus saved):  {format_duration_hm(logged)}  ({logged}s)"
    )

    pause_sec = pause_seconds_from_events(events, end_for_pause)
    rec_sec = total_distraction_recovery_seconds(d_ts, st_sql, end_for_pause)
    eff = attention_quality_effective_seconds(metrics_row, events, d_ts)

    console.print("[bold]Attention quality[/bold] [dim](same rules as reports)[/dim]")
    console.print(
        f"  pause time (session_events):     {format_duration_hms(pause_sec)}  ({pause_sec}s)"
    )
    console.print(
        f"  distraction recovery (capped): {format_duration_hms(rec_sec)}  ({rec_sec}s)  "
        f"[dim]max {DISTRACTION_RECOVERY_CAP_SECONDS // 60}m per distraction[/dim]"
    )

    if eff is None:
        if str(row.get("status")) == "killed":
            console.print("  effective attention:             [dim]n/a (killed session)[/dim]")
            console.print("  attention quality rate:        [dim]n/a[/dim]")
        else:
            console.print("  effective attention:             —")
            console.print("  attention quality rate:        —")
    else:
        console.print(
            f"  effective attention:             {format_duration_hms(eff)}  ({eff}s)"
        )
        if wall_sec and wall_sec > 0:
            aq = attention_quality_rate_value(eff, wall_sec)
            if aq is not None:
                console.print(
                    f"  attention quality rate:        {aq:.3f}   ({eff} / {wall_sec} wall)"
                )
            else:
                console.print("  attention quality rate:        —")
        else:
            console.print("  attention quality rate:        —")

    pause_n = sum(1 for e in events if str(e["event_type"]) == "pause")
    fb_score = focus_block_session_score(metrics_row, pause_n, dc)
    qual = wall_sec is not None and wall_sec >= 25 * 60 and str(row.get("status")) != "killed"
    console.print("[bold]Focus block[/bold] [dim](reference; qualifying = wall ≥25m, not killed)[/dim]")
    console.print(
        f"  pause events: {pause_n}   distractions: {dc}   qualifying: {'yes' if qual else 'no'}"
    )
    console.print(f"  block score (if qualifying):     {fb_score:.2f}")

    if provisional:
        console.print(
            "[dim]Open session: metrics use current UTC as end_time for pause/recovery/wall.[/dim]"
        )

    # --- Events table ---
    ev_table = Table(title="Session events (local time)", show_lines=False)
    ev_table.add_column("#", justify="right", style="dim")
    ev_table.add_column("local time", style="cyan")
    ev_table.add_column("Δ prev", style="yellow")
    ev_table.add_column("type", style="green")
    ev_table.add_column("details", style="white", overflow="fold")

    sorted_ev = sorted(
        [_as_dict(e) for e in events],
        key=lambda r: (str(r["timestamp"]), int(r.get("id") or 0)),
    )
    prev_ts: Optional[Any] = None
    for i, ev in enumerate(sorted_ev, start=1):
        ts_raw = ev.get("timestamp")
        local_ts = format_local(str(ts_raw), timezone_config) if ts_raw else "—"
        if prev_ts is None:
            delta_s = "—"
        else:
            ds = int(
                max(
                    0,
                    (
                        parse_stored_utc(str(ts_raw)) - parse_stored_utc(str(prev_ts))
                    ).total_seconds(),
                )
            )
            delta_s = format_duration_hms(ds)
        prev_ts = ts_raw
        ev_table.add_row(
            str(i),
            local_ts,
            delta_s,
            str(ev.get("event_type") or ""),
            _fmt_event_details(ev.get("details")),
        )
    console.print(ev_table)

    # --- Distractions table ---
    dist_table = Table(title="Distractions", show_lines=False)
    dist_table.add_column("#", justify="right", style="dim")
    dist_table.add_column("local time", style="cyan")
    dist_table.add_column("recovery charge", style="yellow")
    dist_table.add_column("description", style="white", overflow="fold")

    for i, d in enumerate(distractions, start=1):
        ts_raw = d["timestamp"]
        charge = distraction_recovery_charge_seconds(
            str(ts_raw), st_sql, end_for_pause
        )
        desc = (d["description"] or "").strip() or "—"
        dist_table.add_row(
            str(i),
            format_local(str(ts_raw), timezone_config),
            format_duration_hms(charge),
            desc,
        )
    if distractions:
        console.print(dist_table)
    else:
        console.print("[dim]No distractions logged.[/dim]")


def run_session_inspect(
    session_ids: List[int],
    timezone_config: str,
    console: Console,
) -> None:
    for i, sid in enumerate(session_ids):
        if i:
            console.print()
        _print_one_session(sid, timezone_config, console)
