#!/usr/bin/env python3
import os
import re
from datetime import datetime, timezone
from pathlib import Path

def main():
    root_dir = Path(__file__).parent.parent
    pyproject_path = root_dir / "pyproject.toml"
    
    # Read version from pyproject.toml
    version = "0.0.0"
    if pyproject_path.exists():
        content = pyproject_path.read_text()
        match = re.search(r'^version\s*=\s*"([^"]+)"', content, re.MULTILINE)
        if match:
            version = match.group(1)
            
    # Generate stamp
    timestamp = datetime.now(timezone.utc).strftime("%Y.%m.%d.%H%M")
    build_stamp = f"{version}.dev{timestamp}"
    
    # Write Python build info
    build_info_path = root_dir / "pomocli" / "_build_info.py"
    build_info_path.write_text(
        f'# GENERATED FILE - DO NOT EDIT\n'
        f'__version__ = "{version}"\n'
        f'__build__ = "{build_stamp}"\n'
    )
    
    print(f"{build_stamp}")

if __name__ == "__main__":
    main()
