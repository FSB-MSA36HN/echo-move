import logging

import uvicorn

from .config import get_settings


def main() -> None:
    cfg = get_settings()
    log = logging.getLogger("echo_move")
    uvicorn.run("echo_move.app:app", host=cfg.host, port=cfg.port, log_level="warning")
    log.info("stopped")


if __name__ == "__main__":
    main()
