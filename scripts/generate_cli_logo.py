#!/usr/bin/env python3
"""Regenerate terminal ASCII logo for `pomo logo` from assets/pomocli-status-icon.png.

Maps luminance to a multi-character ramp (smoother than binary `#`/space) at higher
column count. Bright-white ANSI on ink. Requires Pillow (dev only).

    uv sync --group dev
    python scripts/generate_cli_logo.py

Or:  poe generate-logo
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image

REPO_ROOT = Path(__file__).resolve().parent.parent
SOURCE_PNG = REPO_ROOT / "assets" / "pomocli-status-icon.png"
OUTPUT_PY = REPO_ROOT / "pomocli" / "ui" / "logo_ansi_generated.py"

# Wider grid = less blocky; terminal cells are ~2× taller than wide.
MAX_WIDTH = 56
# Composite transparent pixels onto black before sampling.
COMPOSITE_BG = (0, 0, 0)
# Below this luminance counts as background (suppress resize noise).
LUM_FLOOR = 10

# Light → heavy ink (no leading space — background is only LUM_FLOOR). Quantized steps
# keep edges smooth without “letter soup” from long ramps.
INK_RAMP = "'`^\",:;~-=+*#%@"


def char_for_luma(v: int) -> str:
    if v < LUM_FLOOR:
        return " "
    t = (v - LUM_FLOOR) / max(255 - LUM_FLOOR, 1)
    n = len(INK_RAMP)
    idx = min(n - 1, int(t * n))
    return INK_RAMP[idx]


def build_grid(gray: Image.Image) -> list[list[str]]:
    w, h = gray.size
    px = gray.load()
    grid: list[list[str]] = []
    for y in range(h):
        row: list[str] = []
        for x in range(w):
            row.append(char_for_luma(int(px[x, y])))
        grid.append(row)
    return grid


def crop_grid(grid: list[list[str]]) -> list[list[str]]:
    h = len(grid)
    if h == 0 or not grid[0]:
        return [[" "]]
    w = len(grid[0])
    min_r, max_r = h, -1
    min_c, max_c = w, -1
    for r in range(h):
        for c in range(w):
            if grid[r][c] != " ":
                min_r = min(min_r, r)
                max_r = max(max_r, r)
                min_c = min(min_c, c)
                max_c = max(max_c, c)
    if max_r < 0:
        return [[" "]]
    return [row[min_c : max_c + 1] for row in grid[min_r : max_r + 1]]


def grid_to_lines(grid: list[list[str]]) -> list[str]:
    """Bright white ink; spaces stay normal gaps."""
    lines: list[str] = []
    for row in grid:
        body = "".join(row).rstrip()
        if body:
            lines.append(f"\033[1;37m{body}\033[0m")
    return lines


def main() -> None:
    if not SOURCE_PNG.is_file():
        raise SystemExit(f"Missing source image: {SOURCE_PNG}")

    rgba = Image.open(SOURCE_PNG).convert("RGBA")
    bg = Image.new("RGB", rgba.size, COMPOSITE_BG)
    bg.paste(rgba, mask=rgba.split()[3])
    w0, h0 = bg.size
    new_w = min(MAX_WIDTH, w0)
    new_h = max(1, int((h0 / w0) * new_w / 2))
    small = bg.resize((new_w, new_h), Image.Resampling.LANCZOS)
    gray = small.convert("L")

    grid = crop_grid(build_grid(gray))
    ncols = len(grid[0]) if grid else 0
    lines = grid_to_lines(grid)

    header = (
        "# AUTO-GENERATED FILE — DO NOT EDIT.\n"
        "# Regenerate with: python scripts/generate_cli_logo.py  (or: poe generate-logo)\n"
        "# Source: assets/pomocli-status-icon.png (luminance ramp ASCII + bright-white ANSI)\n"
        "\n"
        "LOGO_ANSI_LINES: tuple[str, ...] = (\n"
    )
    body = "".join(f"    {line!r},\n" for line in lines)
    footer = ")\n"
    OUTPUT_PY.write_text(header + body + footer, encoding="utf-8")
    print(f"Wrote {len(lines)} lines ({ncols} chars wide) to {OUTPUT_PY}")


if __name__ == "__main__":
    main()
