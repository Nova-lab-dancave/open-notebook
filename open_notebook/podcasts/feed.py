"""Build the Podcast Feed (RSS 2.0 with iTunes tags). See CONTEXT.md."""

import os
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import format_datetime
from typing import Optional

from open_notebook.exceptions import ConfigurationError

ITUNES_NS = "http://www.itunes.com/dtds/podcast-1.0.dtd"
ATOM_NS = "http://www.w3.org/2005/Atom"
ET.register_namespace("itunes", ITUNES_NS)
ET.register_namespace("atom", ATOM_NS)

DEFAULT_TITLE = "Open Notebook Podcasts"
DEFAULT_AUTHOR = "Open Notebook"
DEFAULT_DESCRIPTION = "Podcast episodes generated in Open Notebook."
DEFAULT_LANGUAGE = "en"


def _itunes(tag: str) -> str:
    return f"{{{ITUNES_NS}}}{tag}"


@dataclass(frozen=True)
class FeedItem:
    """One Published Episode as a feed item."""

    title: str
    description: str
    published_at: datetime  # timezone-aware
    guid: str
    enclosure_url: str
    enclosure_bytes: int
    enclosure_type: str
    duration_seconds: int


def resolve_public_base_url(
    forwarded_proto: Optional[str] = None, forwarded_host: Optional[str] = None
) -> str:
    """Return the HTTPS origin podcast apps should use to reach this API.

    Sources, first HTTPS one wins: OPEN_NOTEBOOK_PUBLIC_URL, then API_URL (the
    browser-facing origin the deployment already sets), then the forwarded
    headers. Podcast apps need absolute URLs and Apple Podcasts expects HTTPS,
    so a source that is not HTTPS is skipped.

    Raises:
        ConfigurationError: no source gives an HTTPS origin.
    """
    candidates = [os.environ.get("OPEN_NOTEBOOK_PUBLIC_URL"), os.environ.get("API_URL")]
    if forwarded_host:
        proto = (forwarded_proto or "").split(",")[0].strip()
        host = forwarded_host.split(",")[0].strip()
        candidates.append(f"{proto}://{host}")
    for candidate in candidates:
        if candidate and candidate.strip().lower().startswith("https://"):
            return candidate.strip().rstrip("/")
    raise ConfigurationError(
        "The Podcast Feed needs an HTTPS address. Set OPEN_NOTEBOOK_PUBLIC_URL "
        "to the HTTPS origin podcast apps should use (for example "
        "https://your-host.your-tailnet.ts.net:8502)."
    )


def build_feed_xml(
    feed_url: str, base_url: str, items: Optional[list[FeedItem]] = None
) -> bytes:
    """Serialise the Podcast Feed: default show info plus one item per episode."""
    rss = ET.Element("rss", {"version": "2.0"})
    channel = ET.SubElement(rss, "channel")
    ET.SubElement(channel, "title").text = DEFAULT_TITLE
    ET.SubElement(channel, "link").text = base_url
    ET.SubElement(channel, "description").text = DEFAULT_DESCRIPTION
    ET.SubElement(channel, "language").text = DEFAULT_LANGUAGE
    ET.SubElement(
        channel,
        f"{{{ATOM_NS}}}link",
        {"href": feed_url, "rel": "self", "type": "application/rss+xml"},
    )
    ET.SubElement(channel, _itunes("author")).text = DEFAULT_AUTHOR
    # Private feed: keep it out of Apple's public directory.
    ET.SubElement(channel, _itunes("block")).text = "yes"
    for item in items or []:
        element = ET.SubElement(channel, "item")
        ET.SubElement(element, "title").text = item.title
        ET.SubElement(element, "description").text = item.description
        ET.SubElement(element, "pubDate").text = format_datetime(
            item.published_at.astimezone(timezone.utc), usegmt=True
        )
        ET.SubElement(element, "guid", {"isPermaLink": "false"}).text = item.guid
        ET.SubElement(
            element,
            "enclosure",
            {
                "url": item.enclosure_url,
                "length": str(item.enclosure_bytes),
                "type": item.enclosure_type,
            },
        )
        ET.SubElement(element, _itunes("duration")).text = str(item.duration_seconds)
    return ET.tostring(rss, encoding="utf-8", xml_declaration=True)
