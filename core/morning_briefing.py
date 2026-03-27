"""Morning briefing — fetches news headlines and compiles a spoken summary."""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Optional

from utils.logger import logger

# RSS feeds to try, in priority order
_FEEDS = [
    ("BBC News", "https://feeds.bbci.co.uk/news/rss.xml"),
    ("Hacker News", "https://hnrss.org/frontpage"),
    ("TechCrunch", "https://techcrunch.com/feed/"),
]

_NUM_HEADLINES = 3


def _ordinal(n: int) -> str:
    """Return ordinal string for a day number (1st, 2nd, 3rd, ...)."""
    if 11 <= n <= 13:
        return f"{n}th"
    return f"{n}{('th','st','nd','rd','th','th','th','th','th','th')[n % 10]}"


async def fetch_morning_briefing(name: str = "Sidhanth") -> str:
    """Build a morning briefing string with date/time and top news headlines.

    Runs the RSS fetch in a thread so it doesn't block the event loop.
    Returns a natural-language string suitable for TTS.
    """
    now = datetime.now()
    day_name = now.strftime("%A")          # e.g. "Thursday"
    month_name = now.strftime("%B")        # e.g. "March"
    day_ord = _ordinal(now.day)            # e.g. "27th"
    time_str = now.strftime("%I:%M %p").lstrip("0")  # e.g. "9:05 AM"

    greeting = f"Good morning {name}! It's {day_name}, {month_name} {day_ord}. The time is {time_str}."

    # Fetch headlines in a thread (feedparser does blocking I/O)
    headlines = await asyncio.to_thread(_fetch_headlines)

    if headlines:
        parts = [f"{i}. {title}" for i, title in enumerate(headlines, 1)]
        headline_text = " ".join(parts)
        return f"{greeting} Here are today's top headlines: {headline_text}"
    else:
        return f"{greeting} I wasn't able to fetch the latest news headlines right now."


def _fetch_headlines() -> list[str]:
    """Try each RSS feed until we get headlines. Returns up to _NUM_HEADLINES titles."""
    try:
        import feedparser
    except ImportError:
        logger.error("feedparser not installed — cannot fetch news headlines")
        return []

    for feed_name, feed_url in _FEEDS:
        try:
            logger.debug("Morning briefing: trying {} ({})", feed_name, feed_url)
            feed = feedparser.parse(feed_url)
            if feed.bozo and not feed.entries:
                logger.warning("Feed {} returned bozo error: {}", feed_name, feed.bozo_exception)
                continue

            titles = []
            for entry in feed.entries[:_NUM_HEADLINES]:
                title = entry.get("title", "").strip()
                if title:
                    titles.append(title)

            if titles:
                logger.info("Morning briefing: got {} headlines from {}", len(titles), feed_name)
                return titles

        except Exception:
            logger.exception("Morning briefing: failed to fetch {}", feed_name)
            continue

    logger.warning("Morning briefing: all feeds failed")
    return []
