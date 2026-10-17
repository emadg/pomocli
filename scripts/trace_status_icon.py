#!/usr/bin/env python3
"""Trace the shared macOS status icon into a themeable SVG.

Requires Pillow and Potrace for regeneration only; neither is needed by the
widget. Run: python3 scripts/trace_status_icon.py [--potrace /path/to/potrace]
"""

import argparse
from pathlib import Path
import subprocess
import tempfile
import xml.etree.ElementTree as ET

from PIL import Image


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--potrace", default="potrace")
    args = parser.parse_args()
    root = Path(__file__).resolve().parent.parent
    source = root / "assets/pomocli-status-icon.png"
    output = source.with_suffix(".svg")
    with Image.open(source) as image:
        width, height = image.size
        # The Mac icon is an alpha template. Trace its opacity, not its white
        # RGB pixels, to preserve the transparent terminal cutouts.
        mask = image.convert("RGBA").getchannel("A").point(
            lambda alpha: 0 if alpha >= 128 else 255, mode="1"
        )
    with tempfile.TemporaryDirectory(prefix="pomo-icon-trace-") as directory:
        bitmap = Path(directory) / "mask.pbm"
        vector = Path(directory) / "trace.svg"
        mask.save(bitmap)
        subprocess.run(
            [args.potrace, "--svg", "--flat", "--turdsize", "16",
             "--opttolerance", "0.2", "--output", str(vector), str(bitmap)],
            check=True,
        )
        traced = ET.parse(vector).getroot()
    group = traced.find("{http://www.w3.org/2000/svg}g")
    if group is None:
        raise SystemExit("Potrace did not produce an SVG path group")
    transform = group.attrib["transform"]
    paths = [" ".join(path.attrib["d"].split()) for path in group]
    output.write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">\n'
        '  <!-- Traced from pomocli-status-icon.png; regenerate with scripts/trace_status_icon.py. -->\n'
        '  <style id="current-color-scheme">.ColorScheme-Text { color: #232629; }</style>\n'
        f'  <g class="ColorScheme-Text" fill="currentColor" stroke="none" transform="{transform}">\n'
        + "".join(f'    <path d="{path}"/>\n' for path in paths)
        + '  </g>\n</svg>\n',
        encoding="utf-8",
    )
    print(f"{output.relative_to(root)}: {output.stat().st_size} bytes (source: {source.stat().st_size})")


if __name__ == "__main__":
    main()
