"""
maestro_flow_triage.py
======================
Scans #help-maestro-flow for new messages/threads that @mention Shield team members.
For each unprocessed mention:
  1. Fetches the full thread context
  2. Uses a LangChain LLM agent to classify ownership (Shield IS vs Flow team)
     and draft a contextual Slack reply — grounded in CODEOWNERS
  3. Sends the draft to Baishali via Telegram DM for approval
  4. Saves pending state so maestro_flow_approval_poster.py can post on approval

Approval commands (reply in Telegram to the draft message):
  "post"          → send draft as-is
  "post: <text>"  → send custom text
  "skip"          → discard

LLM setup:
  Requires ANTHROPIC_API_KEY in keyring:
    py -c "import keyring; keyring.set_password('hermes', 'ANTHROPIC_API_KEY', 'sk-ant-...')"
  Model: claude-haiku-4-5 (fast + cheap for triage)
"""

import os, sys, json, time, re, requests, keyring
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
from typing import Literal

# ── Auth ──────────────────────────────────────────────────────────────────────
load_dotenv(r"C:\Users\Baishali.Ghosh\AppData\Local\hermes\.env")

SLACK_TOKEN      = keyring.get_password("hermes", "SLACK_BOT_TOKEN")
TG_TOKEN         = os.environ.get("TELEGRAM_BOT_TOKEN", "")
ANTHROPIC_API_KEY = keyring.get_password("hermes", "ANTHROPIC_API_KEY") or \
                    os.environ.get("ANTHROPIC_API_KEY", "")
TG_CHAT_ID       = "8588389643"   # Baishali's private DM

# ── Config ────────────────────────────────────────────────────────────────────
CHANNEL_ID       = "C0AE5U60686"   # #help-maestro-flow
LOOKBACK_H       = 48
STATE_FILE       = os.path.join(os.path.dirname(__file__), "maestro_flow_triage_state.json")
CODEOWNERS_CACHE = os.path.join(os.path.dirname(__file__), "codeowners_cache.json")

SLACK_HEADERS    = {"Authorization": f"Bearer {SLACK_TOKEN}"}

# ── Shield team ───────────────────────────────────────────────────────────────
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

# ── LangChain agent ───────────────────────────────────────────────────────────

def _load_codeowners_context() -> str:
    """Load CODEOWNERS cache and format it as a compact context string for the LLM."""
    if not os.path.exists(CODEOWNERS_CACHE):
        return "(CODEOWNERS cache not found — use general IS/Flow knowledge)"

    with open(CODEOWNERS_CACHE) as f:
        cache = json.load(f)

    shield_paths = []
    for repo, paths in cache.get("shield_is_paths", {}).items():
        for p in paths:
            shield_paths.append(f"  {repo}: {p}")

    flow_paths = []
    for repo, paths in cache.get("flow_team_paths", {}).items():
        for p in paths:
            flow_paths.append(f"  {repo}: {p}")

    refreshed = cache.get("last_refreshed", "unknown")[:10]
    return f"""CODEOWNERS snapshot (refreshed {refreshed}):

Shield IS team owns these paths (owners: @rahul-katikineni @mukundbayyaram @rohitinu @baishalighosh):
{chr(10).join(shield_paths)}

Flow team owns these paths (default: @UiPath/portal-members + studioweb-fe):
{chr(10).join(flow_paths[:8])}
  (and everything else not listed above)"""


def _build_system_prompt(codeowners_ctx: str) -> str:
    return f"""You are a triage agent for the UiPath Integration Service (IS) Shield team.
Your job is to read a Slack thread from #help-maestro-flow and determine:
1. Which team owns the issue — Shield IS, Flow team, or Shared
2. Draft a short, helpful reply to post in-thread

## Team ownership guide

**Shield IS team** owns:
- The DAP (integration-service-design-time) adapter — the connector activity panel in Flow/VSCode
- The MFE (Micro Frontend) — connector properties UI, connection picker, connection expiry
- Connector manifest mapping, connector registry, connector serialization
- The connector-activity package in StudioWeb
- Integration Service backend — connectors API, IS SDK, coded workflows, API Workflow runtime
- Connection/authentication issues with specific connectors (Salesforce, Snowflake, HubSpot, etc.)
- HTTP connector, credential/token failures, connector schema issues

**Flow team** owns:
- The Flow canvas, workflow engine, schema versioning, flow execution runtime
- Triggers, agent orchestration, Maestro/MST runtime, BPMN
- StudioWeb canvas UI (non-DAP parts), node rendering, sequence/loop logic
- Everything else in flow-workbench not listed as Shield-owned

**Shared** = issue spans both (e.g. connector not discoverable in Flow search — IS owns the data, Flow owns the UI)

{codeowners_ctx}

## Output format
Respond with a JSON object (no markdown, no preamble):
{{
  "owner": "Shield" | "Flow" | "Shared",
  "confidence": "high" | "medium" | "low",
  "reasoning": "<1-2 sentences explaining the call>",
  "draft_reply": "<the Slack reply to post in-thread — friendly, concise, ≤3 sentences. Use Slack mrkdwn. Do NOT include @mentions of Shield members — the script adds those. If Flow-owned: say you're routing to the Flow team. If Shield-owned: say the IS/Shield team is on it and will follow up. If Shared: say both teams will coordinate.>"
}}"""


def classify_with_llm(thread_text: str, reporter_name: str) -> dict:
    """
    Call Claude via LangChain to classify ownership and draft a reply.
    Returns dict with keys: owner, confidence, reasoning, draft_reply.
    Falls back to rule-based classification if LLM unavailable.
    """
    if not ANTHROPIC_API_KEY:
        print("  [LLM] No ANTHROPIC_API_KEY — using rule-based fallback")
        return _classify_fallback(thread_text)

    try:
        from langchain_anthropic import ChatAnthropic
        from langchain_core.messages import HumanMessage, SystemMessage

        codeowners_ctx = _load_codeowners_context()
        system_prompt  = _build_system_prompt(codeowners_ctx)

        llm = ChatAnthropic(
            model="claude-haiku-4-5",
            api_key=ANTHROPIC_API_KEY,
            temperature=0,
            max_tokens=512,
        )

        user_msg = f"""Reporter: {reporter_name}

Thread content:
{thread_text[:3000]}

Classify ownership and draft the reply."""

        response = llm.invoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_msg),
        ])

        raw = response.content.strip()
        # Strip markdown code fences if present
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)

        result = json.loads(raw)
        # Validate required fields
        assert result.get("owner") in ("Shield", "Flow", "Shared")
        assert result.get("confidence") in ("high", "medium", "low")
        assert result.get("draft_reply")
        print(f"  [LLM] owner={result['owner']} confidence={result['confidence']}")
        return result

    except json.JSONDecodeError as e:
        print(f"  [LLM] JSON parse error: {e} — raw: {raw[:200]}")
        return _classify_fallback(thread_text)
    except Exception as e:
        print(f"  [LLM] Error: {e} — using rule-based fallback")
        return _classify_fallback(thread_text)


def _classify_fallback(text: str) -> dict:
    """
    Rule-based fallback (original keyword approach) used when LLM unavailable.
    Loads signals from CODEOWNERS cache if available.
    """
    t = text.lower()

    # Load from cache
    shield_kw, flow_kw = [], []
    if os.path.exists(CODEOWNERS_CACHE):
        with open(CODEOWNERS_CACHE) as f:
            cache = json.load(f)
        shield_kw = cache.get("shield_is_keywords", [])
        flow_kw   = cache.get("flow_team_keywords", [])

    # Hardcoded core signals
    SHIELD_CORE = [
        r"\bdap\b", r"\bmfe\b", r"\bactivity[\s-]config\b", r"\bactivity panel\b",
        r"\bproperties[\s-]panel\b", r"\bconnector[\s-]properties\b",
        r"\bconnection[\s-]picker\b", r"\bconnector[\s-]manifest\b",
        r"\bintegration[\s-]service\b", r"\bcredential", r"\btoken\s+(expir|invalid|refresh)",
        r"\bconnect(?:or)?\s+(fail|error|issue|broken|not\s+work)",
    ]
    FLOW_CORE = [
        r"\bworkflow\s+engine\b", r"\bflow[\s-]schema\b", r"\bcanvas\b",
        r"\btrigger\s+(fail|not\s+fire|not\s+work)\b", r"\borchestrat",
        r"\bmaestro\b", r"\bmst\b", r"\bexecution\s+(fail|stuck)",
    ]

    all_shield = SHIELD_CORE + [re.escape(k) for k in shield_kw]
    all_flow   = FLOW_CORE   + [re.escape(k) for k in flow_kw]

    shield_hits = [p for p in all_shield if re.search(p, t)]
    flow_hits   = [p for p in all_flow   if re.search(p, t)]

    if shield_hits and not flow_hits:
        owner, conf = "Shield", "high" if len(shield_hits) >= 2 else "medium"
    elif flow_hits and not shield_hits:
        owner, conf = "Flow", "high" if len(flow_hits) >= 2 else "medium"
    elif shield_hits and flow_hits:
        owner, conf = "Shared", "low"
    else:
        owner, conf = "Unclear", "low"

    if owner == "Shield":
        draft = "Thanks for reaching out! The IS/Shield team is on this — we'll investigate and follow up shortly."
    elif owner == "Flow":
        draft = "Thanks for flagging! This looks like a Flow/Maestro-side issue — routing to the Flow team to pick up."
    elif owner == "Shared":
        draft = "Thanks! This spans both the connector (IS) and workflow execution (Flow) layers — both teams will coordinate and follow up."
    else:
        draft = "Thanks for reaching out! Looking into this and will get back with the right owner shortly."

    return {
        "owner":       owner,
        "confidence":  conf,
        "reasoning":   f"Rule-based: {len(shield_hits)} shield signals, {len(flow_hits)} flow signals",
        "draft_reply": draft,
    }


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
    msgs, cursor = [], None
    while True:
        params = {"channel": channel_id, "oldest": oldest_ts, "limit": 200}
        if cursor:
            params["cursor"] = cursor
        data = slack_get("conversations.history", params)
        if not data.get("ok"):
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
    return f"https://uipath.enterprise.slack.com/archives/{channel_id}/p{ts.replace('.', '')}"


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
        print(f"  TG send error: {d.get('error_code')} {d.get('description')}")
    except Exception as e:
        print(f"  TG send failed: {e}")
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


# ── Thread text formatter ─────────────────────────────────────────────────────
def _format_thread_for_llm(root_text: str, replies: list, id_to_name: dict) -> str:
    """
    Render thread as readable plain text for the LLM.
    Resolves <@UXXX> → display names.
    """
    def resolve_mentions(text):
        return re.sub(
            r"<@(U[A-Z0-9]+)>",
            lambda m: f"@{id_to_name.get(m.group(1), m.group(1))}",
            text
        )
    def strip_slack_markup(text):
        text = re.sub(r"<https?://[^|>]+\|([^>]+)>", r"\1", text)  # links
        text = re.sub(r"<[^>]+>", "", text)                          # remaining tags
        return text.strip()

    lines = ["[Root message]", strip_slack_markup(resolve_mentions(root_text))]
    for rep in replies[1:]:  # skip root (already included)
        user = id_to_name.get(rep.get("user", ""), rep.get("user", "Unknown"))
        body = strip_slack_markup(resolve_mentions(rep.get("text", "")))
        if body:
            lines.append(f"\n[Reply from {user}]\n{body}")
    return "\n".join(lines)


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    if not SLACK_TOKEN:
        print("ERROR: SLACK_BOT_TOKEN not found in keyring"); sys.exit(1)
    if not TG_TOKEN:
        print("ERROR: TELEGRAM_BOT_TOKEN not found in .env"); sys.exit(1)
    if not ANTHROPIC_API_KEY:
        print("WARNING: ANTHROPIC_API_KEY not set — will use rule-based fallback classifier")
        print("  To enable LLM: py -c \"import keyring; keyring.set_password('hermes', 'ANTHROPIC_API_KEY', 'sk-ant-...')\"")

    state    = load_state()
    seen_ts  = set(state.get("seen_ts", []))
    pending  = state.get("pending", {})
    now_ts   = time.time()

    # Prune stale pending (> 7 days)
    pending = {k: v for k, v in pending.items() if now_ts - float(k) < 7 * 86400}

    oldest_ts = str((datetime.now(timezone.utc) - timedelta(hours=LOOKBACK_H)).timestamp())
    messages  = get_channel_history(CHANNEL_ID, oldest_ts)

    # Build a display-name lookup for all users encountered (cache per run)
    _name_cache = {}
    def get_name(uid):
        if uid not in _name_cache:
            _name_cache[uid] = SHIELD_ID_TO_NAME.get(uid) or get_user_display_name(uid)
        return _name_cache[uid]

    new_items = 0
    for msg in messages:
        ts          = msg.get("ts", "")
        text        = msg.get("text", "")
        user        = msg.get("user", "")
        reply_count = msg.get("reply_count", 0)

        if ts in seen_ts or ts in pending:
            continue

        # ── Fetch thread ──────────────────────────────────────────────────────
        replies = []
        if reply_count > 0:
            replies = get_thread_replies(CHANNEL_ID, ts)

        # ── Check for Shield @mention ─────────────────────────────────────────
        all_texts   = [text] + [r.get("text", "") for r in replies[1:]]
        all_combined = " ".join(all_texts)
        mentioned_ids = set(re.findall(r"<@(U[A-Z0-9]+)>", all_combined))
        shield_mentioned = mentioned_ids & SHIELD_MEMBER_IDS

        if not shield_mentioned:
            seen_ts.add(ts)
            continue

        # ── Already-routed check ──────────────────────────────────────────────
        # Skip if a Shield member already replied, or our bot already posted
        TRIAGE_SENTINEL = "Shield/IS team"
        already_routed  = False
        for rep in replies[1:]:
            rep_user = rep.get("user", "")
            rep_text = rep.get("text", "")
            if rep_user in SHIELD_MEMBER_IDS:
                already_routed = True
                print(f"  skip {ts}: already replied by {SHIELD_ID_TO_NAME.get(rep_user, rep_user)}")
                break
            if TRIAGE_SENTINEL in rep_text or "Flow team" in rep_text or "Flow Team" in rep_text:
                already_routed = True
                print(f"  skip {ts}: triage reply already posted")
                break

        if already_routed:
            seen_ts.add(ts)
            continue

        # ── LangChain classification + draft ──────────────────────────────────
        reporter_name = get_name(user) if user else "Unknown"
        thread_text   = _format_thread_for_llm(text, replies, _name_cache | SHIELD_ID_TO_NAME)
        result        = classify_with_llm(thread_text, reporter_name)

        owner      = result["owner"]
        confidence = result["confidence"]
        reasoning  = result.get("reasoning", "")
        draft      = result["draft_reply"]

        # Append cc mentions to draft
        cc = ", ".join(f"<@{uid}>" for uid in shield_mentioned)
        draft_with_cc = f"{draft}\n\n_cc: {cc}_"

        # ── Build Telegram approval message ───────────────────────────────────
        thread_url  = ts_to_url(CHANNEL_ID, ts)
        dt_str      = datetime.fromtimestamp(float(ts), tz=timezone.utc).strftime("%b %d %H:%M UTC")
        preview     = re.sub(r"<[^>]+>", "", text).strip()[:280]
        owner_emoji = {"Shield": "🔵", "Flow": "🟢", "Shared": "🟡"}.get(owner, "⚪")
        mentioned_names = [SHIELD_ID_TO_NAME.get(uid, uid) for uid in shield_mentioned]

        tg_msg = (
            f"🔔 *#help-maestro-flow triage*\n\n"
            f"📅 {dt_str} | 👤 {reporter_name}\n"
            f"🔗 {thread_url}\n\n"
            f"*Preview:* `{preview}`\n\n"
            f"{owner_emoji} *{owner} team* ({confidence} confidence)\n"
            f"_{reasoning}_\n\n"
            f"*Shield members mentioned:* {', '.join(mentioned_names)}\n\n"
            f"*Draft reply:*\n```\n{draft_with_cc}\n```\n\n"
            f"Reply `post` to send · `post: <text>` to edit · `skip` to discard\n"
            f"_(ref: {ts})_"
        )

        tg_msg_id = tg_send(tg_msg)

        if tg_msg_id:
            pending[ts] = {
                "channel_id":     CHANNEL_ID,
                "thread_ts":      ts,
                "thread_url":     thread_url,
                "draft":          draft_with_cc,
                "classification": {"owner": owner, "confidence": confidence},
                "reporter":       reporter_name,
                "tg_msg_id":      tg_msg_id,
                "mentioned_ids":  list(shield_mentioned),
                "created_at":     now_ts,
                "classified_by":  "llm" if ANTHROPIC_API_KEY else "rules",
            }
            new_items += 1
            print(f"  queued: {ts} | {owner} ({confidence}) | {reporter_name}")
        else:
            print(f"  TG send failed for {ts} — marking seen")

        seen_ts.add(ts)
        time.sleep(1)

    state["seen_ts"]  = sorted(seen_ts)[-2000:]
    state["pending"]  = pending
    save_state(state)

    mode = "LLM (Claude)" if ANTHROPIC_API_KEY else "rule-based fallback"
    print(f"\nDone [{mode}]. {new_items} new item(s) queued. {len(pending)} total pending.")


if __name__ == "__main__":
    main()
