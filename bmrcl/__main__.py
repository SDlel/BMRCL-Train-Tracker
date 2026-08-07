"""Allow ``python -m bmrcl`` to launch the dashboard."""

from .app import main

if __name__ == "__main__":
    raise SystemExit(main())
