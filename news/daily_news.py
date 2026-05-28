"""
daily_news.py — Fetch top daily news headlines and print a formatted digest.

Uses RSS feeds (no API key required by default).
Optionally upgrades to NewsAPI if NEWSAPI_KEY is set.

ENV VARS (set in ../.env or export before running):
  NEWS_MAX_ITEMS      — headlines per category (default: 4)
  NEWS_FEED_WORLD     — RSS URL for world news
  NEWS_FEED_TECH      — RSS URL for tech news
  NEWS_FEED_BUSINESS  — RSS URL for business news
  NEWS_FEED_AI        — RSS URL for AI/science news
  NEWSAPI_KEY         — (optional) NewsAPI.org key for richer results
  NEWSAPI_COUNTRY     — country code for NewsAPI top headlines (default: us)
"""

import os
import sys
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

# ── Load .env from repo root (one level up) if present ─────────────────────
def _load_dotenv(env_path: Path) -> None:
    """Minimal .env loader — no external deps needed."""
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key and key not in os.environ:   # don't override real env vars
            os.environ[key] = val

_load_dotenv(Path(__file__).parent.parent / ".env")

# ── Config from env vars ────────────────────────────────────────────────────
MAX_ITEMS = int(os.getenv("NEWS_MAX_ITEMS", "4"))

RSS_FEEDS = {
    "🌍 World":      os.getenv("NEWS_FEED_WORLD",    "https://feeds.bbci.co.uk/news/world/rss.xml"),
    "💻 Technology": os.getenv("NEWS_FEED_TECH",     "https://feeds.bbci.co.uk/news/technology/rss.xml"),
    "💼 Business":   os.getenv("NEWS_FEED_BUSINESS", "https://feeds.bbci.co.uk/news/business/rss.xml"),
    "🤖 AI & Science": os.getenv("NEWS_FEED_AI",    "https://www.sciencedaily.com/rss/computers_math/artificial_intelligence.xml"),
}

NEWSAPI_KEY     = os.getenv("NEWSAPI_KEY", "")
NEWSAPI_COUNTRY = os.getenv("NEWSAPI_COUNTRY", "us")


# ── Fetchers ────────────────────────────────────────────────────────────────
def fetch_rss(url: str) -> list[dict]:
    """Fetch and parse an RSS feed, return list of {title, link}."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "HermesBot/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = resp.read()
        root = ET.fromstring(data)
        items = []
        for item in root.iter("item"):
            title_el = item.find("title")
            link_el  = item.find("link")
            if title_el is not None and title_el.text:
                items.append({
                    "title": title_el.text.strip(),
                    "link":  link_el.text.strip() if link_el is not None and link_el.text else "",
                })
            if len(items) >= MAX_ITEMS:
                break
        return items
    except Exception as e:
        return [{"title": f"⚠️ Could not fetch feed: {e}", "link": ""}]


def fetch_newsapi(category: str = "general") -> list[dict]:
    """Fetch top headlines from NewsAPI (requires NEWSAPI_KEY)."""
    url = (
        f"https://newsapi.org/v2/top-headlines"
        f"?country={NEWSAPI_COUNTRY}&category={category}&pageSize={MAX_ITEMS}"
        f"&apiKey={NEWSAPI_KEY}"
    )
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "HermesBot/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = __import__("json").loads(resp.read())
        return [{"title": a["title"], "link": a["url"]} for a in data.get("articles", [])]
    except Exception as e:
        return [{"title": f"⚠️ NewsAPI error: {e}", "link": ""}]


# ── Digest builder ──────────────────────────────────────────────────────────
def build_digest() -> str:
    today = datetime.now().strftime("%A, %d %B %Y")
    lines = [f"📰 *Daily News Digest — {today}*\n"]

    for category, url in RSS_FEEDS.items():
        lines.append(f"\n*{category}*")
        items = fetch_rss(url)
        for item in items:
            title = item["title"]
            link  = item["link"]
            lines.append(f"• [{title}]({link})" if link else f"• {title}")

    lines.append("\n_Delivered by Hermes_ 🤖")
    return "\n".join(lines)


if __name__ == "__main__":
    print(build_digest())
