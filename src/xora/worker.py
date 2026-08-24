from __future__ import annotations

import logging
import time

from xora.application.pipeline import PredictionPlatform
from xora.config.settings import get_settings
from xora.persistence.db import apply_schema


def main() -> None:
    settings = get_settings()
    logging.basicConfig(level=settings.log_level, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    log = logging.getLogger("xora.worker")
    apply_schema()
    platform = PredictionPlatform()
    log.info("worker started; cycle every %ss", settings.cycle_seconds)
    while True:
        try:
            result = platform.run_cycle()
            log.info(
                "cycle complete predictions=%s validated=%s qualified=%s errors=%s",
                len(result["predictions"]),
                result["validated"],
                result["qualified"],
                result["errors"],
            )
        except Exception:
            log.exception("cycle crashed")
        time.sleep(max(settings.cycle_seconds, 30))


if __name__ == "__main__":
    main()
