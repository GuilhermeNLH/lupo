"""Entry point for Dental Router."""
from __future__ import annotations

import sys
from pathlib import Path

# Ensure the project root is on sys.path so that `app.*` imports work
# when the script is executed directly or via PyInstaller.
_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from app.gui import DentalRouterApp  # noqa: E402
from app.logger import logger         # noqa: E402


def main() -> None:
    logger.info("Starting Dental Router …")
    app = DentalRouterApp()
    app.mainloop()
    logger.info("Dental Router exited.")


if __name__ == "__main__":
    main()
