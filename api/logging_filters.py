"""Log filters for the API process."""

import logging
import re
from typing import Any

# "/api/podcasts/feed/" followed by the token: everything up to the next "/",
# "?", "#", quote or whitespace. Also matches a mistyped URL with no path after
# the token, which still 404s and gets logged.
_FEED_TOKEN = re.compile(r"(/api/podcasts/feed/)[^/?#\s\"']+")


def _redact(value: Any) -> Any:
    if isinstance(value, str):
        return _FEED_TOKEN.sub(r"\1<redacted>", value)
    return value


class RedactFeedToken(logging.Filter):
    """Keep the Feed Token out of log records (see the podcast feed ADR).

    The token is a URL path segment, so server access logs would record it.
    Redacts the message text and every string argument, and never drops a
    record. Tailscale Serve and Cloudflare logs are out of scope.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = _redact(record.msg)
        if isinstance(record.args, tuple):
            record.args = tuple(_redact(a) for a in record.args)
        elif isinstance(record.args, dict):
            record.args = {k: _redact(v) for k, v in record.args.items()}
        return True
