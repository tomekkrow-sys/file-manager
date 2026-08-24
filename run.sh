#!/usr/bin/env python3
"""Wrapper runner dla File Managera."""
import sys
from pathlib import Path

# dodaj core i ui do ścieżki
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent / "core"))
sys.path.insert(0, str(Path(__file__).parent / "ui"))

from file_manager import main

if __name__ == "__main__":
    sys.exit(main())
