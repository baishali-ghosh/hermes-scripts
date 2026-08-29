"""
maestro_flow_approval_poster.py
================================
Polls Telegram for Baishali's approval replies to triage drafts, then posts
the approved reply to the correct Slack thread.

Expected Telegram reply format (in reply to the triage draft message):
  - "post"          → post the draft as-is
  - "post: <text>"  → post custom text instead of the draft
  - "skip"          → discard this item (don't post)

The script uses getUpdates to fetch recent Telegram messages from Baishali's DM,
matches them against pending triage items by tg_msg_id (reply_to_message.message_id),
and posts to Slack accordingly.

State file shared with maestro_flow_triage.py:
  maestro_flow_triage_state.json
  { "seen_ts": [...], "pending": { "<slack_ts>": { ...item... } } }
"""

import os, sys, json, time, re, requests, keyring
from dotenv import load_dotenv
from datetime import datetime, timezone

load_dotenv(r"C:\Users\Baishali.Ghosh\AppData\Local\hermes\.env")

SLACK_TOKEN  = keyring.get_password("hermes", "SLACK_BOT_TOKEN")
TG_TOKEN     = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TG_CHAT_ID   = "8588389643"   # Baishali's private DM
TG_USER_ID   = 8588389643     # same — this is her personal DM chat_id (also her user_id for private chat)

STATE_FILE   = os.path.join(os.path.dirname(__file__), "maestro_flow_triage_state.json")
OFFSET_FILE  = os.path.join(os.path.dirname(__file__), "maestro_flow_tg_offset.json")

SLACK_HEADERS = {"Authorization": f"Bearer {SLACK_TOKEN}"}


# ── State ─────────────────────────────────────────────────────────────────────
def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {"seen_ts": [], "pending": {}}


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def load_offset():
    if os.path.exists(OFFSET_FILE):
        with open(OFFSET_FILE) as f:
            return json.load(f).get("offset", 0)
    return 0


def save_offset(offset):
    with open(OFFSET_FILE, "w") as f:
        json.dump({"offset": offset}, f)


# ── Telegram ──────────────────────────────────────────────────────────────────
def tg_get_updates(offset):
    url = f"https://api.telegram.org/bot{TG_TOKEN}/getUpdates"
    params = {"offset": offset, "limit": 50, "timeout": 5,
              "allowed_updates": ["message"]}
    try:
        r = requests.get(url, params=params, timeout=15)
        d = r.json()
        if d.get("ok"):
            return d.get("result", [])
    except Exception as e:
        print(f"TG getUpdates failed: {e}")
    return []


def tg_send(text, parse_mode="Markdown"):
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    payload = {"chat_id": TG_CHAT_ID, "text": text, "parse_mode": parse_mode,
               "disable_web_page_preview": True}
    try:
        r = requests.post(url, json=payload, timeout=10)
        return r.json().get("ok", False)
    except Exception as e:
        print(f"TG send failed: {e}")
        return False


# ── Slack ─────────────────────────────────────────────────────────────────────
def slack_post_reply(channel_id, thread_ts, text):
    payload = {
        "channel":   channel_id,
        "thread_ts": thread_ts,
        "text":      text,
        "mrkdwn":    True,
    }
    try:
        r = requests.post(
            "https://slack.com/api/chat.postMessage",
            headers={**SLACK_HEADERS, "Content-Type": "application/json"},
            json=payload, timeout=15,
        )
        d = r.json()
        if d.get("ok"):
            return True, d["ts"]
        return False, d.get("error", "unknown")
    except Exception as e:
        return False, str(e)


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    if not SLACK_TOKEN:
        print("ERROR: SLACK_BOT_TOKEN not found in keyring")
        sys.exit(1)
    if not TG_TOKEN:
        print("ERROR: TELEGRAM_BOT_TOKEN not found in .env")
        sys.exit(1)

    state  = load_state()
    offset = load_offset()
    pending = state.get("pending", {})

    if not pending:
        print("No pending items — nothing to do.")
        # Still drain TG updates to keep offset moving
        updates = tg_get_updates(offset)
        if updates:
            save_offset(updates[-1]["update_id"] + 1)
        return

    # Build lookup: tg_msg_id → slack_ts
    tg_id_to_ts = {
        str(item["tg_msg_id"]): slack_ts
        for slack_ts, item in pending.items()
        if "tg_msg_id" in item
    }

    updates  = tg_get_updates(offset)
    max_upd  = offset
    acted    = 0

    for upd in updates:
        uid = upd.get("update_id", 0)
        if uid >= max_upd:
            max_upd = uid + 1

        msg = upd.get("message", {})
        if not msg:
            continue

        # Must be from Baishali's private DM chat
        chat_id = str(msg.get("chat", {}).get("id", ""))
        if chat_id != TG_CHAT_ID:
            continue

        # Must be a reply to one of our triage draft messages
        reply_to = msg.get("reply_to_message", {})
        if not reply_to:
            continue

        replied_msg_id = str(reply_to.get("message_id", ""))
        if replied_msg_id not in tg_id_to_ts:
            continue

        slack_ts = tg_id_to_ts[replied_msg_id]
        item = pending.get(slack_ts)
        if not item:
            continue

        text_raw = msg.get("text", "").strip()
        text_lower = text_raw.lower()

        if text_lower == "skip":
            print(f"Skipped: {slack_ts}")
            del pending[slack_ts]
            tg_send(f"✅ Skipped — triage item discarded.\n_(ref: {slack_ts})_")
            acted += 1
            continue

        if text_lower == "post" or text_lower.startswith("post:"):
            # Determine final text
            if text_lower == "post":
                final_text = item["draft"]
            else:
                # "post: <custom text>" — everything after "post: "
                final_text = re.sub(r"(?i)^post:\s*", "", text_raw).strip()
                if not final_text:
                    tg_send(f"⚠️ `post:` with no text — resending with draft. Reply `skip` to discard.\n_(ref: {slack_ts})_")
                    continue

            # Post to Slack
            ok, result = slack_post_reply(item["channel_id"], item["thread_ts"], final_text)
            if ok:
                thread_url = item.get("thread_url", "")
                tg_send(
                    f"✅ *Posted to Slack!*\n"
                    f"🔗 {thread_url}\n\n"
                    f"*Posted:*\n```\n{final_text[:400]}\n```"
                )
                print(f"Posted to Slack thread {slack_ts}: OK (ts={result})")
                del pending[slack_ts]
                acted += 1
            else:
                tg_send(f"❌ Slack post failed: `{result}`\nRetry by replying `post` again.")
                print(f"Slack post failed for {slack_ts}: {result}")
            continue

        # Unrecognized reply — remind about format
        # Only nudge if it's short (to avoid nudging on unrelated conversation)
        if len(text_raw) < 200:
            tg_send(
                f"⚠️ Not recognized. For triage item `{slack_ts}`:\n"
                f"• `post` — send draft as-is\n"
                f"• `post: <text>` — send custom text\n"
                f"• `skip` — discard"
            )

    save_offset(max_upd)
    state["pending"] = pending
    save_state(state)

    print(f"Done. {acted} action(s) taken. {len(pending)} items still pending.")


if __name__ == "__main__":
    main()
