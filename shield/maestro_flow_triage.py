"""
maestro_flow_triage.py
======================
Scans #help-maestro-flow for new messages/threads that @mention Shield team members.
For each unprocessed mention:
  1. Fetches the thread context
  2. Classifies ownership: Shield (IS) vs Flow team
  3. Drafts a triage reply
  4. Sends draft to Baishali via Telegram DM for approval
  5. Saves pending state so the approval_poster can pick it up

Approval flow (separate cron - maestro_flow_approval_poster.py):
  Baishali replies "post" → post as-is
  Baishali replies "post: <text>" → post edited text
  Baishali replies "skip" → discard

Classification uses:
  - Keyword signals from message text
  - Known Shield IS surface from CODEOWNERS (dap/, mfe/, connector*, connection*)
  - Known Flow surface (canvas, node, trigger, orchestration, schema, workflow engine)
"""

import os, sys, json, time, re, requests, keyring
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

# ── Auth ────────────────────────────────────────────────────────────────────
load_dotenv(r"C:\Users\Baishali.Ghosh\AppData\Local\hermes\.env")

SLACK_TOKEN  = keyring.get_password("hermes", "SLACK_BOT_TOKEN")
TG_TOKEN     = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TG_CHAT_ID   = "8588389643"   # Baishali's private DM

# ── Config ───────────────────────────────────────────────────────────────────
CHANNEL_ID   = "C0AE5U60686"   # #help-maestro-flow
LOOKBACK_H   = 48               # scan last 48h of messages on each run
STATE_FILE        = os.path.join(os.path.dirname(__file__), "maestro_flow_triage_state.json")
CODEOWNERS_CACHE  = os.path.join(os.path.dirname(__file__), "codeowners_cache.json")

SLACK_HEADERS = {"Authorization": f"Bearer {SLACK_TOKEN}"}


# ── Load CODEOWNERS-derived keyword signals ───────────────────────────────────
def _load_codeowners_signals():
    if os.path.exists(CODEOWNERS_CACHE):
        with open(CODEOWNERS_CACHE) as f:
            cache = json.load(f)
        return (
            [re.escape(k) for k in cache.get("shield_is_keywords", [])],
            [re.escape(k) for k in cache.get("flow_team_keywords", [])],
        )
    return [], []

_SHIELD_CO_SIGNALS, _FLOW_CO_SIGNALS = _load_codeowners_signals()


# Shield IS team Slack user IDs (trigger monitoring when any are @mentioned)
SHIELD_MEMBER_IDS = {
    "U02D905FG7J",  # Baishali
    "U092M9RLQ4S",  # Charan
    "U094Q8LQJTA",  # Ojal
    "U029Q2QG1A4",  # Shyam
    "U01SFJWTJPN",  # Mukund
    "U0A4AHF1XHS",  # Rohit
    "U09UG7N0890",  # Pritish
    "U094KENF19P",  # Rahul K
}

SHIELD_ID_TO_NAME = {
    "U02D905FG7J": "Baishali",
    "U092M9RLQ4S": "Charan",
    "U094Q8LQJTA": "Ojal",
    "U029Q2QG1A4": "Shyam",
    "U01SFJWTJPN": "Mukund",
    "U0A4AHF1XHS": "Rohit",
    "U09UG7N0890": "Pritish",
    "U094KENF19P": "Rahul K",
}

# ── Ownership classification ─────────────────────────────────────────────────
# Derived from CODEOWNERS in UiPath/flow-workbench
# Shield IS owns: dap adapter, MFE, connector properties panel, connection picker,
#                 connector manifest mapping, connector registry, connector services API
SHIELD_SIGNALS = [
    # DAP / MFE surface (CODEOWNERS: @rahul-katikineni @mukundbayyaram @rohitinu)
    r"\bdap\b", r"\bdap[\s-]adapter\b", r"\bdap[\s-]http\b",
    r"\bmfe\b", r"\bactivity[\s-]config\b", r"\bactivity panel\b",
    r"\bproperties[\s-]panel\b", r"\bconnector[\s-]properties\b",
    r"\bconnection[\s-]picker\b", r"\bconnection[\s-]expiry\b",
    r"\bconnector[\s-]manifest\b", r"\bconnector[\s-]registry\b",
    r"\bconnector[\s-]icon\b", r"\bconnector[\s-]schema\b",
    # IS service layer
    r"\bintegration[\s-]service\b", r"\bis[\s-]connector\b",
    r"\bshield[\s-]connector\b",
    # Connection / credential issues
    r"\bconnection\s+(not\s+)?work", r"\bauthentication\s+(fail|error|issue)",
    r"\bcredential", r"\btoken\s+(expir|invalid|refresh)",
    r"\bconnect(?:or)?\s+fail", r"\bconnect(?:or)?\s+error",
    r"\bconnect(?:or)?\s+issue", r"\bconnect(?:or)?\s+not\s+work",
    r"\bconnect(?:or)?\s+bug", r"\bconnect(?:or)?\s+broken",
    r"\bconnect(?:or)?\s+not\s+show",
    # Specific connector names (IS-owned)
    r"\bsalesforce\b", r"\bhubspot\b", r"\bsnowflake\b", r"\bslack[\s-]connect",
    r"\bjira[\s-]connect", r"\bgoogle[\s-]sheet", r"\bzendesk\b",
    # HTTP connector / coded workflows (IS SDK)
    r"\bhttp[\s-]connector\b", r"\bcoded[\s-]workflow\b", r"\bis[\s-]sdk\b",
    r"\bapi[\s-]workflow\b",
]

FLOW_SIGNALS = [
    # Flow engine / canvas
    r"\bworkflow\s+engine\b", r"\bworkflow\s+schema\b", r"\bworkflow\s+version",
    r"\bcanvas\b", r"\bflow[\s-]schema\b", r"\bflow[\s-]versioning\b",
    r"\bflow[\s-]builder\b",
    # Trigger / orchestration
    r"\btrigger\s+(not\s+)?fire", r"\btrigger\s+(fail|error|issue|not\s+work)",
    r"\borchestrat", r"\bagent[\s-]run\b",
    # StudioWeb / VSCode UI (non-DAP)
    r"\bstudio[\s-]web\b", r"\bvsix\b",
    r"\bflow[\s-]editor\b", r"\bnode\s+(fail|error|missing|not\s+show)",
    r"\bconnection\s+between\s+node", r"\bsequence\b", r"\bloop\b",
    # Maestro / MST
    r"\bmaestro\b", r"\bmst\b", r"\bagent[\s-]fabric\b", r"\bbpmn\b",
    r"\bprocess[\s-]mining\b",
    # Execution runtime (not IS)
    r"\bexecution\s+(fail|error|stuck|hang)", r"\bqueue\b", r"\bjob\s+(fail|stuck)",
    r"\brobots?\b",
]

AMBIGUOUS_CONNECTOR_IN_FLOW = [
    # These look like connector issues but are about connector discovery in Flow UI
    r"\bconnector\s+(not\s+)?show\s+in\s+flow",
    r"\bconnector\s+(not\s+)?appear\s+in\s+flow",
    r"\bconnect\s+activity\s+(not\s+)?show",
    r"\bdiscover\s+connector",
    r"\bsearch.*connector.*flow",
]


def classify(text: str) -> dict:
    """Return {'owner': 'Shield'|'Flow'|'Shared', 'confidence': 'high'|'medium'|'low', 'signals': [...]}"""
    t = text.lower()

    # Combine hardcoded + CODEOWNERS-derived signals
    all_shield = SHIELD_SIGNALS + _SHIELD_CO_SIGNALS
    all_flow   = FLOW_SIGNALS   + _FLOW_CO_SIGNALS

    shield_hits = [p for p in all_shield if re.search(p, t)]
    flow_hits   = [p for p in all_flow   if re.search(p, t)]
    amb_hits    = [p for p in AMBIGUOUS_CONNECTOR_IN_FLOW if re.search(p, t)]

    # Ambiguous connector-in-flow → shared
    if amb_hits:
        return {"owner": "Shared", "confidence": "medium",
                "signals": [f"ambiguous: {h}" for h in amb_hits]}

    if shield_hits and not flow_hits:
        conf = "high" if len(shield_hits) >= 2 else "medium"
        return {"owner": "Shield", "confidence": conf, "signals": shield_hits[:3]}
    if flow_hits and not shield_hits:
        conf = "high" if len(flow_hits) >= 2 else "medium"
        return {"owner": "Flow", "confidence": conf, "signals": flow_hits[:3]}
    if shield_hits and flow_hits:
        # Both → lean Shield if DAP/MFE signals present, else Shared
        dap_mfe = [s for s in shield_hits if any(k in s for k in ["dap", "mfe", "activ"])]
        if dap_mfe:
            return {"owner": "Shield", "confidence": "medium",
                    "signals": shield_hits[:2] + [f"(also flow: {flow_hits[0]})"][:1]}
        return {"owner": "Shared", "confidence": "low",
                "signals": shield_hits[:2] + flow_hits[:2]}
    return {"owner": "Unclear", "confidence": "low", "signals": []}


# ── Slack helpers ─────────────────────────────────────────────────────────────
def slack_get(endpoint, params, retries=3):
    for attempt in range(retries):
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


def get_channel_history(channel_id, oldest_ts):
    msgs = []
    cursor = None
    while True:
        params = {"channel": channel_id, "oldest": oldest_ts, "limit": 200}
        if cursor:
            params["cursor"] = cursor
        data = slack_get("conversations.history", params)
        if not data.get("ok"):
            # Try joining if not in channel
            if data.get("error") == "not_in_channel":
                import urllib.request, urllib.parse
                req_data = urllib.parse.urlencode({"channel": channel_id}).encode()
                req = urllib.request.Request(
                    "https://slack.com/api/conversations.join", data=req_data,
                    headers={**SLACK_HEADERS, "Content-Type": "application/x-www-form-urlencoded"})
                urllib.request.urlopen(req)
                data = slack_get("conversations.history", params)
            else:
                break
        msgs.extend(data.get("messages", []))
        if not data.get("has_more"):
            break
        cursor = data.get("response_metadata", {}).get("next_cursor")
        if not cursor:
            break
    return msgs


def get_thread_replies(channel_id, thread_ts):
    data = slack_get("conversations.replies",
                     {"channel": channel_id, "ts": thread_ts, "limit": 50})
    return data.get("messages", [])


def get_user_display_name(user_id):
    data = slack_get("users.info", {"user": user_id})
    if data.get("ok"):
        u = data["user"]
        return u.get("real_name") or u.get("name") or user_id
    return user_id


def ts_to_url(channel_id, ts):
    ts_clean = ts.replace(".", "")
    return f"https://uipath.enterprise.slack.com/archives/{channel_id}/p{ts_clean}"


# ── Telegram helpers ──────────────────────────────────────────────────────────
def tg_send(text, parse_mode="Markdown"):
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    payload = {"chat_id": TG_CHAT_ID, "text": text, "parse_mode": parse_mode,
               "disable_web_page_preview": True}
    try:
        r = requests.post(url, json=payload, timeout=10)
        d = r.json()
        if d.get("ok"):
            return d["result"]["message_id"]
    except Exception as e:
        print(f"TG send failed: {e}")
    return None


# ── State management ──────────────────────────────────────────────────────────
def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {"seen_ts": [], "pending": {}}


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    if not SLACK_TOKEN:
        print("ERROR: SLACK_BOT_TOKEN not found in keyring")
        sys.exit(1)
    if not TG_TOKEN:
        print("ERROR: TELEGRAM_BOT_TOKEN not found in .env")
        sys.exit(1)

    state = load_state()
    seen_ts = set(state.get("seen_ts", []))
    pending = state.get("pending", {})

    # Prune stale pending entries (> 7 days old)
    now_ts = time.time()
    pending = {k: v for k, v in pending.items()
               if now_ts - float(k) < 7 * 86400}

    oldest_ts = str((datetime.now(timezone.utc) - timedelta(hours=LOOKBACK_H)).timestamp())
    messages = get_channel_history(CHANNEL_ID, oldest_ts)

    new_items = 0
    for msg in messages:
        ts    = msg.get("ts", "")
        text  = msg.get("text", "")
        user  = msg.get("user", "")
        reply_count = msg.get("reply_count", 0)

        if ts in seen_ts:
            continue
        if ts in pending:
            continue

        # Check if any Shield member is @mentioned in root or thread
        mentioned_ids = set(re.findall(r"<@(U[A-Z0-9]+)>", text))
        replies = []

        if reply_count > 0:
            replies = get_thread_replies(CHANNEL_ID, ts)
            for rep in replies[1:]:  # skip root
                rep_text = rep.get("text", "")
                mentioned_ids |= set(re.findall(r"<@(U[A-Z0-9]+)>", rep_text))

        shield_mentioned = mentioned_ids & SHIELD_MEMBER_IDS
        if not shield_mentioned:
            seen_ts.add(ts)
            continue

        # ── Already-routed check ──────────────────────────────────────────────
        # If a Shield member already posted a reply in this thread, it's handled.
        # Also skip if our bot already posted a triage reply (sentinel text present).
        TRIAGE_SENTINEL = "Shield/IS Team"  # present in all our draft replies
        already_routed = False
        for rep in replies[1:]:  # skip root message
            rep_user = rep.get("user", "")
            rep_text = rep.get("text", "")
            # Shield member replied directly
            if rep_user in SHIELD_MEMBER_IDS:
                already_routed = True
                print(f"  skip {ts}: already replied by Shield member {SHIELD_ID_TO_NAME.get(rep_user, rep_user)}")
                break
            # Bot already posted our triage reply
            if TRIAGE_SENTINEL in rep_text or "Flow Team" in rep_text:
                already_routed = True
                print(f"  skip {ts}: triage reply already posted by bot")
                break

        if already_routed:
            seen_ts.add(ts)
            continue

        # Gather full thread text for classification
        all_text = text
        for rep in replies[1:]:
            all_text += " " + rep.get("text", "")

        classification = classify(all_text)
        mentioned_names = [SHIELD_ID_TO_NAME.get(uid, uid) for uid in shield_mentioned]
        reporter_name   = get_user_display_name(user) if user else "Unknown"
        thread_url      = ts_to_url(CHANNEL_ID, ts)
        dt_str = datetime.fromtimestamp(float(ts), tz=timezone.utc).strftime("%b %d %H:%M UTC")

        # Build preview (first 300 chars of root message)
        preview = re.sub(r"<@U[A-Z0-9]+>", lambda m: f"@{SHIELD_ID_TO_NAME.get(m.group(1), m.group(1))}", text)
        preview = re.sub(r"<[^>]+>", "", preview).strip()[:300]

        # Build triage reply draft
        owner = classification["owner"]
        confidence = classification["confidence"]

        if owner == "Shield":
            team_label = "🔵 *Shield/IS Team*"
            suggested_action = "I'll look into this — let me investigate and follow up."
            owner_mention = f"<@U02D905FG7J>"  # Baishali (can be adjusted)
        elif owner == "Flow":
            team_label = "🟢 *Flow Team*"
            suggested_action = "This looks like a Flow/Maestro-side issue. Routing to the Flow team."
            owner_mention = None
        elif owner == "Shared":
            team_label = "🟡 *Shared (Shield + Flow)*"
            suggested_action = "This spans both connector config (IS) and workflow execution (Flow). We'll coordinate and follow up."
            owner_mention = None
        else:
            team_label = "⚪ *Owner Unclear*"
            suggested_action = "Looking into this and will get back with the right owner."
            owner_mention = None

        draft_slack_reply = (
            f"Thanks for reaching out! {team_label} is on this.\n\n"
            f"{suggested_action}\n\n"
            f"_Triage confidence: {confidence} | cc: {', '.join(f'<@{uid}>' for uid in shield_mentioned)}_"
        )

        # Send Telegram DM for approval
        tg_msg = (
            f"🔔 *#help-maestro-flow triage*\n\n"
            f"📅 {dt_str} | 👤 {reporter_name}\n"
            f"🔗 {thread_url}\n\n"
            f"*Message preview:*\n`{preview}`\n\n"
            f"*Classification:* {team_label} ({confidence} confidence)\n"
            f"*Shield members mentioned:* {', '.join(mentioned_names)}\n\n"
            f"*Draft reply:*\n```\n{draft_slack_reply}\n```\n\n"
            f"Reply `post` to send as-is, `post: <your text>` to customize, or `skip` to discard.\n"
            f"_(ref: {ts})_"
        )
        tg_msg_id = tg_send(tg_msg)

        if tg_msg_id:
            pending[ts] = {
                "channel_id":      CHANNEL_ID,
                "thread_ts":       ts,
                "thread_url":      thread_url,
                "draft":           draft_slack_reply,
                "classification":  classification,
                "reporter":        reporter_name,
                "tg_msg_id":       tg_msg_id,
                "mentioned_ids":   list(shield_mentioned),
                "created_at":      now_ts,
            }
            new_items += 1
            print(f"Queued for approval: {ts} ({owner}, {confidence})")
        else:
            print(f"TG send failed for {ts} — marking seen to avoid re-scan")

        seen_ts.add(ts)
        time.sleep(1)  # gentle rate limit

    # Keep seen_ts bounded (last 2000 entries)
    seen_list = sorted(seen_ts)[-2000:]

    state["seen_ts"] = seen_list
    state["pending"] = pending
    save_state(state)

    print(f"Done. {new_items} new item(s) queued for approval. {len(pending)} total pending.")


if __name__ == "__main__":
    main()
