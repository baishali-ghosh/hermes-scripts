"""
daily_news.py -- Daily news digest: India, Tech/AI, Finance.

ENV VARS (set in ../.env or export before running):
  NEWS_MAX_ITEMS          -- headlines per category (default: 5)
  NEWS_FEED_INDIA         -- India general news RSS
  NEWS_FEED_TECH          -- Tech news RSS
  NEWS_FEED_AI            -- AI-specific news RSS
  NEWS_FEED_FINANCE_IN    -- India finance/markets RSS
  NEWS_FEED_FINANCE_WORLD -- Global finance RSS
  NEWSAPI_KEY             -- (optional) NewsAPI.org key
  NEWSAPI_COUNTRY         -- NewsAPI country code (default: in)
"""

import os
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path


# -- .env loader (no external deps) ------------------------------------------
def _load_dotenv(env_path: Path) -> None:
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = val

_load_dotenv(Path(__file__).parent.parent / ".env")


# -- Config from env vars -----------------------------------------------------
MAX_ITEMS = int(os.getenv("NEWS_MAX_ITEMS", "5"))

RSS_FEEDS = {
    "\U0001f1ee\U0001f1f3 India Headlines": os.getenv(
        "NEWS_FEED_INDIA",
        "https://feeds.bbci.co.uk/news/world/asia/india/rss.xml"
    ),
    "\U0001f4bb Tech & AI": os.getenv(
        "NEWS_FEED_TECH",
        "https://techcrunch.com/feed/"
    ),
    "\U0001f916 AI Updates": os.getenv(
        "NEWS_FEED_AI",
        "https://www.artificialintelligence-news.com/feed/"
    ),
    "\U0001f4c8 India Finance & Markets": os.getenv(
        "NEWS_FEED_FINANCE_IN",
        "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms"
    ),
    "\U0001f4b9 Global Finance": os.getenv(
        "NEWS_FEED_FINANCE_WORLD",
        "https://feeds.bbci.co.uk/news/business/rss.xml"
    ),
}

NEWSAPI_KEY = os.getenv("NEWSAPI_KEY", "")
NEWSAPI_COUNTRY = os.getenv("NEWSAPI_COUNTRY", "in")


# -- RSS fetcher --------------------------------------------------------------
def fetch_rss(url: str) -> list:
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
                title = title_el.text.strip()
                link = ""
                if link_el is not None:
                    link = (link_el.text or link_el.tail or "").strip()
                items.append({"title": title, "link": link})
            if len(items) >= MAX_ITEMS:
                break
        return items
    except Exception as e:
        return [{"title": f"\u26a0\ufe0f Could not fetch feed: {e}", "link": ""}]


# -- Digest builder -----------------------------------------------------------
def build_digest() -> str:
    today = datetime.now().strftime("%A, %d %B %Y")
    lines = [f"\U0001f4f0 *Daily Digest \u2014 {today}*", ""]

    for category, url in RSS_FEEDS.items():
        lines.append(f"*{category}*")
        for item in fetch_rss(url):
            title = item["title"]
            link  = item["link"]
            lines.append(f"\u2022 [{title}]({link})" if link else f"\u2022 {title}")
        lines.append("")

    lines.append("_Delivered by Hermes \U0001f916_")
    return "\n".join(lines)


if __name__ == "__main__":
    print(build_digest())
