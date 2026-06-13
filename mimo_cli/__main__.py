"""CLI entry point — allows `python -m mimo_cli`."""

import sys
from mimo_cli.cli import main

if __name__ == "__main__":
    sys.exit(main())
