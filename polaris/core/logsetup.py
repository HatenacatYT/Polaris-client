"""ログ設定。機密情報のマスキングと診断用の匿名化を含む。"""
from __future__ import annotations
import collections
import logging
import re
from logging.handlers import RotatingFileHandler
from pathlib import Path

_SECRET = re.compile(
    r"(?i)(\.?ROBLOSECURITY|cookie|token|password|passwd|authorization|secret|api[_-]?key)(\s*[=:]\s*|\s+)([^\s,;\"']+)")
_WARN = re.compile(r"_\|WARNING:[^\s\"']+")


def redact(text: str) -> str:
    text = _SECRET.sub(lambda m: f"{m.group(1)}{m.group(2)}<redacted>", text)
    return _WARN.sub("<redacted>", text)


def anonymize(text: str) -> str:
    import getpass
    text = redact(text)
    home = str(Path.home())
    if home:
        text = re.sub(re.escape(home), "<HOME>", text, flags=re.I)
        text = re.sub(re.escape(home.replace("\\", "/")), "<HOME>", text, flags=re.I)
    try:
        user = getpass.getuser()
        if len(user) >= 3:
            text = re.sub(re.escape(user), "<USER>", text, flags=re.I)
    except Exception:
        pass
    return text


class RedactFilter(logging.Filter):
    def filter(self, record):
        record.msg = redact(record.getMessage())
        record.args = ()
        return True


class MemoryHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.lines: collections.deque[str] = collections.deque(maxlen=3000)

    def emit(self, record):
        try:
            self.lines.append(self.format(record))
        except Exception:
            pass


MEMORY = MemoryHandler()
_FMT = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")


def setup_logging(log_dir: Path, level=logging.INFO) -> logging.Logger:
    logger = logging.getLogger("polaris")
    logger.setLevel(level)
    for h in list(logger.handlers):
        logger.removeHandler(h)
        if isinstance(h, RotatingFileHandler):
            h.close()
    logger.propagate = False
    try:
        Path(log_dir).mkdir(parents=True, exist_ok=True)
        fh = RotatingFileHandler(Path(log_dir) / "polaris.log", maxBytes=1_000_000,
                                 backupCount=3, encoding="utf-8")
        fh.setFormatter(_FMT)
        fh.addFilter(RedactFilter())
        logger.addHandler(fh)
    except OSError:
        pass
    MEMORY.setFormatter(_FMT)
    if not any(isinstance(f, RedactFilter) for f in MEMORY.filters):
        MEMORY.addFilter(RedactFilter())
    logger.addHandler(MEMORY)
    return logger
