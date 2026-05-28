"""
daily_news.py — Fetch top daily news headlines and print a formatted digest.
Uses NewsAPI (free tier) or falls back to RSS feeds (no API key needed).
Designed to be run by Hermes cron and delivered to Telegram.
"""

import urllib.request
import urllib.parse
import json
import xml.etree.ElementTree as ET
from datetime import datetime

# ── RSS feeds (no API key required) ─────────────────────────────────────────
RSS_FEEDS = {
    "🌍 World": "https://feeds.bbci.co.uk/news/world/rss.xml",
    "💻 Technology": "https://feeds.bbci.co.uk/news/technology/rss.xml",
    "💼 Business": "https://feeds.bbci.co.uk/news/business/rss.xml",
    "🤖 AI & Science": "https://www.sciencedaily.com/rss/computers_math/artificial_intelligence.xml",
}

MAX_ITEMS = 4  # headlines per category


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
            link_el = item.find("link")
            if title_el is not None and title_el.text:
                items.append({
                    "title": title_el.text.strip(),
                    "link": link_el.text.strip() if link_el is not None and link_el.text else "",
                })
            if len(items) >= MAX_ITEMS:
                break
        return items
    except Exception as e:
        return [{"title": f"⚠️ Could not fetch feed: {e}", "link": ""}]


def build_digest() -> str:
    today = datetime.now().strftime("%A, %d %B %Y")
    lines = [f"📰 *Daily News Digest — {today}*\n"]

    for category, url in RSS_FEEDS.items():
        lines.append(f"\n*{category}*")
        for item in fetch_rss(url):
            title = item["title"]
            link = item["link"]
            if link:
                lines.append(f"• [{title}]({link})")
            else:
                lines.append(f"• {title}")

    lines.append("\n_Delivered by Hermes_ 🤖")
    return "\n".join(lines)


if __name__ == "__main__":
    print(build_digest())
