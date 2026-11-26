"""One JSON object per application log record, without request payloads."""
from datetime import datetime, timezone
import json
import logging
import sys

from app.config import settings


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "event": record.getMessage(),
        }
        payload.update(getattr(record, "event_fields", {}))
        return json.dumps(payload, ensure_ascii=False)


logger = logging.getLogger("agent")
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(JsonFormatter())
logger.handlers.clear()
logger.addHandler(handler)
logger.setLevel(settings.log_level)
logger.propagate = False


def log_event(event: str, *, level: int = logging.INFO, **fields) -> None:
    logger.log(level, event, extra={"event_fields": fields})
