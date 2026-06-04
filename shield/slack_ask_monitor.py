"""
Slack Ask Monitor — scans 20 channels for unresolved threads mentioning the Shield team.
Outputs JSON summary. Uses a cache file to avoid re-processing old messages.
"""

import keyring, requests, json, time, os
from datetime import datetime, timezone, timedelta

SLACK_TOKEN = keyring.get_password("hermes", "SLACK_BOT_TOKEN")
HEADERS = {"Authorization": f"Bearer {SLACK_TOKEN}"}

CACHE_FILE = os.path.join(os.path.dirname(__file__), "slack_ask_monitor_cache.json")

TEAM_IDS = {
    "Baishali": "U02D905FG7J",
    "Chandu":   "U01SN2RCS73",
    "Charan":   "U092M9RLQ4S",
    # Giri and Mukesh excluded — tags ignored per Naruto
    "Mukund":   "U01SFJWTJPN",
    "Ojal":     "U094Q8LQJTA",
    "Pritish":  "U09UG7N0890",
    "Rahul":    "U094KENF19P",
    "Rohit":    "U0A4AHF1XHS",
    "Sanjeet":  "U06CXP781G8",
    "Shyam":    "U029Q2QG1A4",
}
TEAM_ID_SET = set(TEAM_IDS.values())
ID_TO_NAME  = {v: k for k, v in TEAM_IDS.items()}

CHANNELS = {
    # Customer Issues (generic IS help)
    "C01S63MNGH0": {"name": "#help-integration-platform-experiences", "group": "Customer Issues"},
    "CP14C639T":   {"name": "#help-datafabric",                       "group": "Customer Issues"},
    "C0APWF020DN": {"name": "#help-coding-agents-preview",            "group": "Customer Issues"},
    # X-Team DAP Asks (DAP / Maestro / activity config surface)
    "C0AQ30LMUBZ": {"name": "#help-dap-unification",                  "group": "X-Team DAP Asks"},
    "C0AE5U60686": {"name": "#help-maestro-flow",                     "group": "X-Team DAP Asks"},
    "C074M703U8G": {"name": "#help-maestro",                          "group": "X-Team DAP Asks"},
    "C0ACTJC0NV6": {"name": "#feat-ub-activity-configuration",        "group": "X-Team DAP Asks"},
    # Connector Enhancements — #datafabric-connectors is DUAL-ROUTED (see dual_route below)
    "C08GRNAGLMU": {"name": "#datafabric-connectors",                 "group": "Connector Enhancements",
                    "dual_route": "X-Team DAP Asks",
                    "dual_route_keywords": ["maestro", "dap", "activity", "flow", "studio", "orchestrator",
                                            "ub-", "coded", "vscode", "api workflow"]},
    "CJPB035U2":   {"name": "#is-spectra",                            "group": "Connector Enhancements"},
    # X-team Asks
    "C08THRBQRNH": {"name": "#is-support-eng-collab",                 "group": "X-team Asks"},
    "CR41HADK5":   {"name": "#team-first-party-service-partners",     "group": "X-team Asks"},
    "C081CFJUEHL": {"name": "#feat-po-fe-intsvc-activities",          "group": "X-team Asks"},
    # Feature / Agentic
    "C08JV4S6N11": {"name": "#agentic-push-to-prod",                  "group": "Feature / Agentic"},
    "C08JY9SDN8M": {"name": "#is-dogfooding",                         "group": "Feature / Agentic"},
    "C09CV6G3CER": {"name": "#ipe-automation-suite",                  "group": "Feature / Agentic"},
    # Ops / DRI
    "C06UVQWMVED": {"name": "#integration-platform-experiences-challenges",               "group": "Ops / DRI"},
    "C08DNFAED28": {"name": "#integration-platform-experiences-challenges-working-group", "group": "Ops / DRI"},
    "C7VMYAD26":   {"name": "#integration-platform-experiences-dri",                      "group": "Ops / DRI"},
    # Case Management Asks
    "C08NTKCLY5V": {"name": "#feat-casemanagement", "group": "Case Management Asks"},
    # Team Internal
    "C04QSSY4BNY": {"name": "#ipe-shield-team",                       "group": "Team Internal"},
    "C07S1JJRKLP": {"name": "#is-shield-private",                     "group": "Team Internal"},
    "C01TXCJHWMD": {"name": "#integration-platform-experiences-engineering", "group": "Team Internal"},
    "C066EDZ2MK9": {"name": "#ipe-hydra-team",                        "group": "Team Internal"},
}

RESOLVED_REACTIONS = {
    "white_check_mark", "heavy_check_mark", "done", "checked",
    "resolved", "check", "checkered_flag", "tick", "green_check",
}

LOOKBACK_DAYS = 14
CHANNEL_TIMEOUT_SECS = 15   # max wall-clock seconds to spend on a single channel
GLOBAL_TIMEOUT_SECS  = 90   # bail from all channels if total elapsed exceeds this (leaves 30s buffer before 120s cron kill)


def slack_get(endpoint, params, retries=3):
    for attempt in range(retries):
        try:
            r = requests.get(f"https://slack.com/api/{endpoint}", headers=HEADERS,
                             params=params, timeout=8)  # 8s per request — fail fast
            d = r.json()
            if d.get("ok"):
                return d
            if d.get("error") == "ratelimited":
                wait = min(int(r.headers.get("Retry-After", 5)), 8)  # cap at 8s so we don't blow per-channel budget
                time.sleep(wait)
                continue
            return d
        except Exception:
            time.sleep(5)
    return {}


def is_resolved(reactions):
    return any(r.get("name", "").lower().strip(":") in RESOLVED_REACTIONS
               for r in (reactions or []))


def mentions_team(text):
    return [name for name, uid in TEAM_IDS.items() if f"<@{uid}>" in text]


def get_user_display(uid):
    if uid in ID_TO_NAME:
        return ID_TO_NAME[uid]
    d = slack_get("users.info", {"user": uid})
    if d.get("ok"):
        u = d["user"]
        return u.get("real_name") or u.get("name", uid)
    return uid


# Load cache (maps "channel_id:thread_ts" -> last known state)
cache = {}
if os.path.exists(CACHE_FILE):
    try:
        with open(CACHE_FILE) as f:
            cache = json.load(f)
    except Exception:
        cache = {}

oldest_ts = str((datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)).timestamp())

results = []
seen = set()
SCRIPT_START = time.time()  # global wall-clock guard

for channel_id, meta in CHANNELS.items():
    channel_name  = meta["name"]
    group         = meta["group"]

    # Global guard — if we're close to the 120s cron kill, save cache and stop now
    if time.time() - SCRIPT_START > GLOBAL_TIMEOUT_SECS:
        break

    channel_start = time.time()          # per-channel wall-clock guard

    # Use cached oldest seen ts to avoid re-fetching everything
    channel_oldest = cache.get(f"cursor:{channel_id}", oldest_ts)
    # But don't go further back than LOOKBACK_DAYS
    channel_oldest = max(channel_oldest, oldest_ts)

    data = slack_get("conversations.history", {
        "channel": channel_id,
        "oldest":  channel_oldest,
        "limit":   200,
    })
    if not data.get("ok"):
        continue

    messages = data.get("messages", [])
    if not messages:
        continue

    # Update cursor to latest message ts
    latest_ts = max((m.get("ts", "0") for m in messages), default=channel_oldest)
    cache[f"cursor:{channel_id}"] = latest_ts

    for msg in messages:
        # Per-channel timeout guard — move on if this channel is eating too much time
        if time.time() - channel_start > CHANNEL_TIMEOUT_SECS:
            break

        ts        = msg.get("ts", "")
        text      = msg.get("text", "")
        thread_ts = msg.get("thread_ts", ts)
        reply_count = msg.get("reply_count", 0)

        thread_key = f"{channel_id}:{thread_ts}"
        if thread_key in seen:
            continue

        # Root message mentions?
        mentioned = set(mentions_team(text))

        # Check replies for mentions (only if thread has replies and we haven't cached it)
        # Store fetched replies so dual-route can reuse them without a second API call
        fetched_reply_messages = []
        if reply_count > 0:
            cached_entry   = cache.get(thread_key, {})
            cached_replies = cached_entry.get("reply_count", 0)

            if reply_count != cached_replies:
                # Don't fetch replies if channel is already over budget
                if time.time() - channel_start > CHANNEL_TIMEOUT_SECS:
                    break
                replies_data = slack_get("conversations.replies", {
                    "channel": channel_id, "ts": thread_ts, "limit": 100
                })
                fetched_reply_messages = replies_data.get("messages", [])
                for reply in fetched_reply_messages:
                    mentioned.update(mentions_team(reply.get("text", "")))
                    if is_resolved(reply.get("reactions", [])):
                        mentioned = set()  # mark as resolved — skip
                        cache[thread_key] = {"resolved": True, "reply_count": reply_count}
                        break
                else:
                    cache[thread_key] = {"reply_count": reply_count}

        if not mentioned:
            continue

        # Check root message resolved
        if is_resolved(msg.get("reactions", [])):
            cache[thread_key] = {"resolved": True}
            continue

        # Skip if cached as resolved
        if cache.get(thread_key, {}).get("resolved"):
            continue

        seen.add(thread_key)

        poster_uid = msg.get("user", "")
        poster     = get_user_display(poster_uid)
        msg_date   = datetime.fromtimestamp(float(ts), tz=timezone.utc).strftime("%d %b %Y")
        url        = f"https://uipath.enterprise.slack.com/archives/{channel_id}/p{ts.replace('.', '')}"

        # Dual-route: reuse already-fetched replies — no extra API call
        effective_group = group
        dual_route      = meta.get("dual_route")
        if dual_route:
            keywords   = meta.get("dual_route_keywords", [])
            reply_text = " ".join(r.get("text", "") for r in fetched_reply_messages[:10])
            full_text  = (text + " " + reply_text).lower()
            if any(kw in full_text for kw in keywords):
                effective_group = dual_route

        results.append({
            "channel":      channel_name,
            "channel_id":   channel_id,
            "group":        effective_group,
            "thread_ts":    thread_ts,
            "date":         msg_date,
            "poster":       poster,
            "mentioned":    sorted(mentioned),
            "reply_count":  reply_count,
            "text_preview": text[:300].replace("\n", " "),
            "url":          url,
        })

# Save updated cache
with open(CACHE_FILE, "w") as f:
    json.dump(cache, f)

results.sort(key=lambda x: (x["group"], x["thread_ts"]))
print(json.dumps(results, indent=2))
