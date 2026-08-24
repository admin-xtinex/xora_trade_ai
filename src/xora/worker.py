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
    log.info("worker started; waits for Start trading then runs IST 15m slots")
    while True:
        try:
            result = platform.run_cycle()
            phase = result.get("phase")
            log.info("phase=%s opened=%s closed=%s errors=%s", phase, result.get("opened"), result.get("closed"), result.get("errors"))
            sleep_for = 10 if phase == "live" else 5 if phase == "waiting" else 15
        except Exception:
            log.exception("cycle crashed")
            sleep_for = 15
        time.sleep(sleep_for)


if __name__ == "__main__":
    main()
