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
    log.info("worker started; auto-arms the next IST 15m slot")
    while True:
        try:
            result = platform.run_cycle()
            phase = result.get("phase")
            errors = result.get("errors") or []
            log.info(
                "phase=%s slot=%s opened=%s closed=%s universe=%s engines=%s errors=%s detail=%s",
                phase,
                result.get("slot"),
                result.get("opened"),
                result.get("closed"),
                result.get("universe"),
                result.get("engines"),
                errors[:8],
                result.get("detail"),
            )
            sleep_for = 8 if phase == "live" else 5 if phase == "waiting" else 10
        except Exception:
            log.exception("cycle crashed")
            sleep_for = 15
        time.sleep(sleep_for)


if __name__ == "__main__":
    main()
