"""
coding_agents_tracker.py

Monitors #team-coding-agents (C0A2T23NJ59) for important dev updates.
Classifies messages into signal categories and appends useful ones to the
Shield team canvas (F0B43LH0MDM).

Categories tracked:
  - eval_result      : pass rate announcements, benchmark runs
  - new_feature      : new capabilities, metrics, dashboard updates
  - breaking_change  : removals, deprecations, schedule changes, crashes
  - important_pr     : PRs flagged as important (not routine review requests)
  - announcement     : @channel/@here, scheduled changes, infra updates

Run: every weekday at 9 AM IST via Hermes cron.
"""

import json
import re
import time
import keyring
import requests
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────
SOURCE_CHANNEL = "C0A2T23NJ59"   # #team-coding-agents
DM_CHANNEL     = "D08F22N8Q5B"   # Baishali DM with bot
STATE_FILE     = Path(__file__).parent / "coding_agents_tracker_state.json"
LOOKBACK_HOURS = 25              # slight overlap to avoid missing anything

# ── Classification keywords ───────────────────────────────────────────────────
CATEGORIES = {
    "🚨 Breaking Change": [
        "breaking", "removing", "removed", "deprecat", "no longer",
        "access violation", "crash", "0xC0000005", "rename", "migration",
        "schedule change", "cadence change", "adjusting the cadence",
        "simplify dependency", "remove.*dependency",
    ],
    "📊 Eval Result": [
        "pass rate", "% pass", "eval run", "evalboard", "skills run",
        "coder eval", "nightly run", "full skills", "benchmark",
        "expected turns", "watchlist",
    ],
    "✨ New Feature / Update": [
        "introducing", "new feature", "new metric", "new chart",
        "dashboard update", "few new features", "new goodie",
        "you can now", "we are now", "we're introducing",
        "download entire", "artifact",
    ],
    "📢 Announcement": [
        "<!channel>", "<!here>", "<!subteam^",
        "update to coder", "announcement", "planning to",
        "heads up", "fyi", "cross posting",
    ],
}

# Min reply_count to consider a thread "high engagement" (worth tracking even if unclear)
HIGH_ENGAGEMENT_REPLIES = 5


# ── Helpers ───────────────────────────────────────────────────────────────────

def load_state():
    if STATE_FILE.exists():
        with open(STATE_FILE) as f:
            return json.load(f)
    return {"seen_ts": [], "last_canvas_update": None}


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def slack_get(token, endpoint, params):
    h = {"Authorization": f"Bearer {token}"}
    for attempt in range(3):
        try:
            r = requests.get(f"https://slack.com/api/{endpoint}",
                headers=h, params=params, timeout=15)
            d = r.json()
            if d.get("ok"):
                return d
            if d.get("error") == "ratelimited":
                time.sleep(int(r.headers.get("Retry-After", 10)))
                continue
            return d
        except Exception:
            time.sleep(3)
    return {}


def slack_post(token, channel, text):
    h = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    r = requests.post("https://slack.com/api/chat.postMessage",
        headers=h, json={"channel": channel, "text": text, "mrkdwn": True}, timeout=15)
    return r.json()


def canvas_append(token, canvas_id, markdown_section):
    """Append a section to the canvas."""
    h = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    r = requests.post("https://slack.com/api/canvases.edit",
        headers=h,
        json={
            "canvas_id": canvas_id,
            "changes": [{
                "operation": "insert_at_end",
                "document_content": {
                    "type": "markdown",
                    "markdown": markdown_section,
                }
            }]
        }, timeout=15)
    return r.json()


def strip_slack_formatting(text):
    """Clean up Slack mrkdwn for readable display."""
    text = re.sub(r'<https?://[^|>]+\|([^>]+)>', r'\1', text)  # <url|label> → label
    text = re.sub(r'<https?://[^>]+>', '', text)                # bare URLs removed
    text = re.sub(r'<@[A-Z0-9]+>', '', text)                    # user mentions
    text = re.sub(r'<!subteam\^[^>]+>', '@team', text)          # subteam mentions
    text = re.sub(r'<!channel>', '@channel', text)
    text = re.sub(r'<!here>', '@here', text)
    text = re.sub(r'\*([^*]+)\*', r'**\1**', text)              # bold
    text = re.sub(r'_([^_]+)_', r'*\1*', text)                  # italic
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def classify(text):
    """Return list of matching category labels."""
    lower = text.lower()
    matched = []
    for label, keywords in CATEGORIES.items():
        for kw in keywords:
            if re.search(kw, lower):
                matched.append(label)
                break
    return matched


def extract_links(text):
    """Extract URLs from Slack message text."""
    links = re.findall(r'<(https?://[^|>]+)(?:\|[^>]*)?>',  text)
    return links[:3]  # max 3 links per message


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    token = keyring.get_password("hermes", "SLACK_BOT_TOKEN")
    state = load_state()
    seen_ts = set(state.get("seen_ts", []))

    # Fetch recent messages
    oldest = str((datetime.now(timezone.utc) - timedelta(hours=LOOKBACK_HOURS)).timestamp())
    data   = slack_get(token, "conversations.history",
                       {"channel": SOURCE_CHANNEL, "oldest": oldest, "limit": 100})
    messages = data.get("messages", [])

    # Filter: root messages only (not thread replies), not bots, not seen
    candidates = []
    for m in messages:
        if m.get("subtype"):
            continue
        if m.get("bot_id"):
            continue
        ts = m.get("ts", "")
        if ts in seen_ts:
            continue
        # Skip pure PR review request messages (low signal)
        text = m.get("text", "")
        if re.match(r'^(hey team,?\s*)?(can i please get|need help in review|PTAL|please review)',
                    text.strip(), re.IGNORECASE):
            seen_ts.add(ts)
            continue
        candidates.append(m)

    if not candidates:
        save_state({"seen_ts": list(seen_ts), "last_canvas_update": state.get("last_canvas_update")})
        print("")  # silent
        return

    # Classify and filter to important ones
    important = []
    for m in candidates:
        text      = m.get("text", "")
        ts        = m.get("ts", "")
        replies   = m.get("reply_count", 0)
        labels    = classify(text)
        links     = extract_links(text)
        dt        = datetime.fromtimestamp(float(ts)).strftime("%d %b %Y %H:%M IST")

        seen_ts.add(ts)

        if labels or replies >= HIGH_ENGAGEMENT_REPLIES:
            important.append({
                "ts":      ts,
                "dt":      dt,
                "text":    strip_slack_formatting(text),
                "labels":  labels or ["💬 High Engagement"],
                "links":   links,
                "replies": replies,
                "permalink": f"https://uipath-product.slack.com/archives/{SOURCE_CHANNEL}/p{ts.replace('.', '')}",
            })

    save_state({"seen_ts": list(seen_ts), "last_canvas_update": datetime.now().isoformat()})

    if not important:
        print("")  # nothing worth reporting
        return

    # Build DM message
    today = datetime.now().strftime("%d %b %Y")
    lines = [
        f"📡 *#team-coding-agents — {len(important)} important update(s)* | {today}",
        "",
    ]

    for item in important:
        label_str = " · ".join(item["labels"])
        lines.append(f"*{label_str}*")
        lines.append(f"> {item['text'][:280]}{'...' if len(item['text']) > 280 else ''}")
        link_extras = ""
        if item["links"]:
            link_extras = " · " + " ".join(f"<{l}|link>" for l in item["links"])
        lines.append(f"<{item['permalink']}|→ thread> · {item['dt']}{link_extras}")
        if item["replies"]:
            lines.append(f"_{item['replies']} replies_")
        lines.append("")

    result = slack_post(token, DM_CHANNEL, "\n".join(lines))

    if result.get("ok"):
        print(f"✅ {len(important)} update(s) from #team-coding-agents → DM")
    else:
        print(f"❌ DM failed: {result.get('error')}")
        print("\n".join(lines))  # fallback to stdout


if __name__ == "__main__":
    main()
