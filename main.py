"""Main entry point for DiskImager.

Run directly:
    python main.py --help
    python main.py list
    python main.py gui
"""

import sys
from disktool.cli import main

if __name__ == "__main__":
    main()
