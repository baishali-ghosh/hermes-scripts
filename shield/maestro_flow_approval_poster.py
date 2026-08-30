"""
maestro_flow_approval_poster.py
================================
Polls Baishali's Slack DM for approval replies to triage drafts, then posts
the approved reply to the correct #help-maestro-flow thread.

STRICT RULE: Never posts to Slack without explicit approval from Baishali.

How approval works:
  1. maestro_flow_triage.py detects a new Shield mention in #help-maestro-flow,
     classifies it with the LLM, and sends a draft approval DM to Baishali's
     Slack DM with a dm_ts anchor stored in pending state.
  2. THIS script polls for replies IN THREAD on that DM message.
  3. Baishali replies to the DM thread (thread_ts = dm_ts) with one of:
       "post"         → post the draft as-is
       "post: <text>" → post custom text instead
       "skip"         → discard, do not post
  4. Any other reply is ignored — never posts without explicit "post" or "post:".

State file shared with maestro_flow_triage.py:
  maestro_flow_triage_state.json
  { "seen_ts": [...], "pending": { "<slack_ts>": { "dm_ts": "...", ... } } }
"""

import os, sys, json, re, time, requests, keyring
from dotenv import load_dotenv
from datetime import datetime, timezone

load_dotenv(r"C:\Users\Baishali.Ghosh\AppData\Local\hermes\.env")

SLACK_TOKEN       = keyring.get_password("hermes", "SLACK_BOT_TOKEN")
BAISHALI_SLACK_ID = "U02D905FG7J"

STATE_FILE  = os.path.join(os.path.dirname(__file__), "maestro_flow_triage_state.json")
SEEN_FILE   = os.path.join(os.path.dirname(__file__), "maestro_flow_dm_seen.json")

SLACK_HEADERS = {"Authorization": f"Bearer {SLACK_TOKEN}"}


# ── State ──────────────────────────────────────────────────────────────────────
def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {"seen_ts": [], "pending": {}}


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def load_seen_replies() -> set:
    """Track reply ts values we've already acted on (prevent double-processing)."""
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE) as f:
            return set(json.load(f).get("seen", []))
    return set()


def save_seen_replies(seen: set):
    with open(SEEN_FILE, "w") as f:
        json.dump({"seen": sorted(seen)[-2000:]}, f)


# ── Slack helpers ──────────────────────────────────────────────────────────────
def slack_get(endpoint, params, retries=3):
    for _ in range(retries):
        try:
            r = requests.get(f"https://slack.com/api/{endpoint}",
                             headers=SLACK_HEADERS, params=params, timeout=15)
            d = r.json()
            if d.get("ok"):
                return d
            if d.get("error") == "ratelimited":
                time.sleep(int(r.headers.get("Retry-After", 15)))
                continue
            return d
        except Exception:
            time.sleep(5)
    return {}


def slack_post(endpoint, payload) -> dict:
    try:
        r = requests.post(
            f"https://slack.com/api/{endpoint}",
            headers={**SLACK_HEADERS, "Content-Type": "application/json"},
            json=payload,
            timeout=15,
        )
        return r.json()
    except Exception as e:
        return {"ok": False, "error": str(e)}


def get_dm_channel() -> str:
    """Open (or retrieve) Baishali's DM channel ID."""
    d = slack_post("conversations.open", {"users": BAISHALI_SLACK_ID})
    if d.get("ok"):
        return d["channel"]["id"]
    print(f"  [DM] conversations.open failed: {d.get('error')}")
    return ""


def get_thread_replies(channel_id: str, thread_ts: str) -> list:
    """Fetch all replies in a DM thread. Returns list of message dicts."""
    d = slack_get("conversations.replies",
                  {"channel": channel_id, "ts": thread_ts, "limit": 50})
    msgs = d.get("messages", [])
    # Skip the root message (index 0) — only want replies
    return msgs[1:] if len(msgs) > 1 else []


def post_to_thread(channel_id: str, thread_ts: str, text: str) -> tuple[bool, str]:
    """Post text as a reply in a Slack thread. Returns (ok, ts_or_error)."""
    d = slack_post("chat.postMessage", {
        "channel":   channel_id,
        "thread_ts": thread_ts,
        "text":      text,
        "mrkdwn":    True,
    })
    if d.get("ok"):
        return True, d["ts"]
    return False, d.get("error", "unknown")


def send_dm(dm_channel: str, text: str) -> bool:
    """Send a plain DM to Baishali's DM channel (status updates)."""
    d = slack_post("chat.postMessage", {
        "channel": dm_channel,
        "text":    text,
        "mrkdwn":  True,
    })
    return d.get("ok", False)


# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    if not SLACK_TOKEN:
        print("ERROR: SLACK_BOT_TOKEN not found in keyring")
        sys.exit(1)

    state   = load_state()
    pending = state.get("pending", {})
    seen_replies = load_seen_replies()

    if not pending:
        print("No pending items — nothing to do.")
        return

    dm_channel = get_dm_channel()
    if not dm_channel:
        print("ERROR: Could not open Baishali's Slack DM channel.")
        sys.exit(1)

    acted = 0

    for slack_ts, item in list(pending.items()):
        dm_ts = item.get("dm_ts", "")
        if not dm_ts:
            # Legacy item from old Telegram-based flow — skip, will time out naturally
            print(f"  skip legacy item (no dm_ts): {slack_ts}")
            continue

        # Fetch replies on the DM approval thread
        replies = get_thread_replies(dm_channel, dm_ts)

        for reply in replies:
            reply_ts   = reply.get("ts", "")
            reply_user = reply.get("user", "")
            text_raw   = reply.get("text", "").strip()
            text_lower = text_raw.lower()

            # Only accept replies from Baishali herself
            if reply_user != BAISHALI_SLACK_ID:
                continue

            # Skip replies we've already acted on
            if reply_ts in seen_replies:
                continue

            seen_replies.add(reply_ts)

            # ── SKIP ──
            if text_lower == "skip":
                print(f"  skipped: {slack_ts}")
                del pending[slack_ts]
                send_dm(dm_channel,
                        f"✅ Skipped — triage item discarded.\n_(ref: {slack_ts})_")
                acted += 1
                break

            # ── POST / POST: ──
            if text_lower == "post" or text_lower.startswith("post:"):
                if text_lower == "post":
                    final_text = item["draft"]
                else:
                    final_text = re.sub(r"(?i)^post:\s*", "", text_raw).strip()
                    if not final_text:
                        send_dm(dm_channel,
                                f"⚠️ `post:` with no text — reply again with `post: <your text>` "
                                f"or just `post` to send the draft.\n_(ref: {slack_ts})_")
                        break

                ok, result = post_to_thread(item["channel_id"], item["thread_ts"], final_text)
                if ok:
                    thread_url = item.get("thread_url", "")
                    send_dm(dm_channel,
                            f"✅ *Posted to Slack!*\n"
                            f"🔗 {thread_url}\n\n"
                            f"*Posted:*\n```\n{final_text[:400]}\n```")
                    print(f"  posted: {slack_ts} → {result}")
                    del pending[slack_ts]
                    acted += 1
                else:
                    send_dm(dm_channel,
                            f"❌ Slack post failed: `{result}`\n"
                            f"Reply `post` again to retry.\n_(ref: {slack_ts})_")
                    print(f"  post failed: {slack_ts} — {result}")
                break

            # ── Anything else → silently ignore (never auto-post) ──
            print(f"  unrecognized reply from Baishali (ignored): '{text_raw[:80]}'")

    state["pending"] = pending
    save_state(state)
    save_seen_replies(seen_replies)

    print(f"Done. {acted} action(s) taken. {len(pending)} items still pending.")


if __name__ == "__main__":
    main()
