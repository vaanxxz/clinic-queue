"""
main.py  —  Clinic Queue v6
Application entry point.
"""

from __future__ import annotations

import logging
import sys

import config as C

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(C.DATA_DIR / "clinic.log", encoding="utf-8"),
    ],
)
log = logging.getLogger(__name__)

C.DATA_DIR.mkdir(parents=True, exist_ok=True)


def main() -> None:
    from app import ClinicApp
    import web_server

    log.info("Starting School Clinic Queue Management System v6")

    app = ClinicApp()

    try:
        web_server.start(
            enqueue_callback = app.web_enqueue,
            status_callback  = app.web_get_status,
            host = C.FLASK_HOST,
            port = C.FLASK_PORT,
        )
        log.info("Web check-in live at http://localhost:%d", C.FLASK_PORT)
    except Exception as exc:
        log.warning("Web server could not start: %s", exc)

    app.mainloop()
    log.info("Application closed.")


if __name__ == "__main__":
    main()
