"""
Shield Connector Test Report Monitor
=====================================
Monitors #ipe-shield-team for daily ISNotifications test reports.
When a report with failures is posted, replies in thread tagging connector owners + CC Baishali.

EOD check: scans tracked failure threads for owner responses.
Next-day follow-up: if no legitimate reason given, posts a reminder.

State file: shield_test_report_state.json (same dir as script)

Usage:
  py shield_test_report_monitor.py            # detect new reports + post initial follow-up
  py shield_test_report_monitor.py --followup # check responses + post next-day follow-ups
"""

import keyring
import requests
import json
import os
import re
import sys
from datetime import datetime, timezone, timedelta

# ── Config ───────────────────────────────────────────────────────────────────
CHANNEL_ID = "C04QSSY4BNY"           # #ipe-shield-team
BOT_ID = "B08Q29GSER1"               # ISNotifications bot
STATE_FILE = os.path.join(os.path.dirname(__file__), "shield_test_report_state.json")

# Slack user IDs
BAISHALI = "U02D905FG7J"   # CC on all follow-ups

OWNERS = {
    "sanjeet":  "U06CXP781G8",   # Sanjeet Manna
    "ojal":     "U094Q8LQJTA",   # Ojal Kumar
    "charan":   "U092M9RLQ4S",   # Charan Karpuram
    "mukund":   "U01SFJWTJPN",   # Mukund Bayyaram
    "rahul_k":  "U094KENF19P",   # Rahul Katikineni
    "shyam":    "U029Q2QG1A4",   # Shyam Gupta
}

def uid(name):
    return f"<@{OWNERS[name]}>"

# Connector → owner(s) mapping
CONNECTOR_OWNERS = {
    "uipath-microsoft-teams":                        [uid("sanjeet")],
    "uipath-anthropic-claude":                       [uid("charan")],
    "uipath-google-vertex":                          [uid("sanjeet"), uid("rahul_k")],
    "uipath-microsoft-azureactivedirectory":         [uid("sanjeet")],
    "uipath-microsoft-github":                       [uid("charan"), uid("rahul_k")],
    "uipath-box-box":                                [uid("ojal"), uid("rahul_k")],
    "uipath-uipath-jdbc":                            [uid("charan")],
    "uipath-openai-openai":                          [uid("charan"), uid("rahul_k")],
    "uipath-salesforce-slack":                       [uid("mukund"), uid("sanjeet")],
    "uipath-openai-openaiv1compliant":               [uid("ojal")],
    "uipath-snowflake-snowflake":                    [uid("mukund"), uid("ojal"), uid("charan")],
    "uipath-snowflake-cortex":                       [uid("sanjeet")],
    "uipath-databricks-databricks":                  [uid("ojal"), uid("charan")],
    "uipath-datadog-datadog":                        [uid("charan"), uid("sanjeet")],
    "uipath-amazon-webservices":                     [uid("charan")],
    "uipath-aws-bedrock":                            [uid("charan")],
    "uipath-amazon-sagemaker":                       [uid("ojal")],
    "uipath-microsoft-azure":                        [uid("sanjeet")],
    "uipath-microsoft-azureopenai":                  [uid("ojal")],
    "uipath-microsoft-azureformrecognizer":          [uid("sanjeet")],
    "uipath-microsoft-azureapplicationinsights":     [uid("sanjeet")],
    "uipath-microsoft-activedirectorydomainservices":[uid("sanjeet")],
    "uipath-microsoft-exchangeserver":               [uid("rahul_k")],
    "uipath-microsoft-hyperv":                       [uid("rahul_k")],
    "uipath-microsoft-systemcenter":                 [uid("sanjeet")],
    "uipath-microsoft-translator":                   [uid("ojal")],
    "uipath-microsoft-sentiment":                    [uid("rahul_k")],
    "uipath-microsoft-vision":                       [uid("sanjeet")],
    "uipath-microsoft-powerautomate":                [uid("rahul_k")],
    "uipath-google-cloudplatform":                   [uid("charan")],
    "uipath-google-vision":                          [uid("rahul_k")],
    "uipath-ibm-watsonx":                            [uid("rahul_k")],
    "uipath-jina-jina":                              [uid("ojal")],
    "uipath-perplexity-perplexity":                  [uid("charan")],
    "uipath-pinecone-pinecone":                      [uid("charan")],
    "uipath-netiq-netiq":                            [uid("ojal")],
    "uipath-vmware-vsphere":                         [uid("ojal")],
    "uipath-citrix-hypervisor":                      [uid("rahul_k")],
    "uipath-sap-odata":                              [uid("shyam")],
    "uipath-aws-sqs":                                [uid("charan")],
    "uipath-microsoft-azureaifoundry":               [uid("charan")],
}

# Keywords that suggest a legitimate reason was given in a thread reply
LEGIT_KEYWORDS = [
    "fix", "fixed", "pr", "investigating", "known issue", "flaky", "env issue",
    "infra", "disabled", "deprecated", "will fix", "working on", "root cause",
    "ticket", "jira", "eng", "deployment", "rollback", "config", "credential",
    "expired", "test issue", "false positive", "ignore", "wontfix",
]

# ── State ────────────────────────────────────────────────────────────────────

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {"last_processed_ts": "0", "pending_followup": {}}


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


# ── Slack helpers ─────────────────────────────────────────────────────────────

def slack_get(token, endpoint, **params):
    resp = requests.get(
        f"https://slack.com/api/{endpoint}",
        headers={"Authorization": f"Bearer {token}"},
        params=params
    )
    return resp.json()


def slack_post(token, endpoint, payload):
    resp = requests.post(
        f"https://slack.com/api/{endpoint}",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json=payload
    )
    return resp.json()


# ── Core logic ────────────────────────────────────────────────────────────────

def get_recent_reports(token, since_ts):
    data = slack_get(token, "conversations.history",
                     channel=CHANNEL_ID, oldest=since_ts, limit=10)
    if not data.get("ok"):
        print(f"Error fetching history: {data.get('error')}")
        return []
    reports = []
    for msg in data.get("messages", []):
        if msg.get("bot_id") != BOT_ID:
            continue
        if "🔴" not in msg.get("text", ""):
            continue
        reports.append(msg)
    return reports


def parse_failures(text):
    failures = []
    for line in text.split("\n"):
        if "🔴" not in line:
            continue
        m = re.search(r'🔴\s+(uipath-[\w-]+)', line)
        if not m:
            continue
        connector = m.group(1).strip()
        details = [a for a in re.findall(r'\[([^\]]+)\]', line) if a.lower() != "none"]
        failures.append({"connector": connector, "details": details})
    return failures


def already_replied(token, msg_ts):
    data = slack_get(token, "conversations.replies",
                     channel=CHANNEL_ID, ts=msg_ts, limit=20)
    for reply in data.get("messages", []):
        if "🚨 *Connector Failure Follow-up*" in reply.get("text", ""):
            return True
    return False


def post_followup(token, msg_ts, failures):
    lines = [f"🚨 *Connector Failure Follow-up* — please investigate and share status. CC: <@{BAISHALI}>\n"]
    for f in failures:
        connector = f["connector"]
        owners = CONNECTOR_OWNERS.get(connector, [])
        owner_str = " ".join(owners) if owners else "_(no owner mapped)_"
        detail_str = ", ".join(f"`{d}`" for d in f["details"]) if f["details"] else ""
        if detail_str:
            lines.append(f"• *{connector}* — {detail_str}\n  👉 {owner_str}")
        else:
            lines.append(f"• *{connector}*\n  👉 {owner_str}")

    result = slack_post(token, "chat.postMessage", {
        "channel": CHANNEL_ID,
        "thread_ts": msg_ts,
        "text": "\n".join(lines),
        "mrkdwn": True,
    })
    if result.get("ok"):
        print(f"✅ Posted initial follow-up in thread {msg_ts}")
    else:
        print(f"❌ Failed to post: {result.get('error')}")
    return result.get("ok", False)


def has_legit_response(token, msg_ts, owner_ids):
    """
    Check if any connector owner replied to the thread with a legit reason.
    Returns True if a substantive owner reply exists.
    """
    data = slack_get(token, "conversations.replies",
                     channel=CHANNEL_ID, ts=msg_ts, limit=50)
    replies = data.get("messages", [])[1:]  # skip the original message

    for reply in replies:
        sender = reply.get("user", "")
        text = reply.get("text", "").lower()
        # Check if from an owner (extract raw user IDs from owner mention strings)
        owner_raw_ids = [o.strip("<@>") for o in owner_ids]
        if sender not in owner_raw_ids and sender != BAISHALI:
            continue
        if any(kw in text for kw in LEGIT_KEYWORDS):
            return True
        # Any reply with >10 chars from an owner counts as engagement
        if len(text.strip()) > 10:
            return True
    return False


def post_nextday_followup(token, msg_ts, pending):
    """Post a next-day reminder for connectors with no legit response."""
    lines = [f"📌 *Next-day follow-up* — no update received yesterday. <@{BAISHALI}> FYI\n"]
    for entry in pending:
        connector = entry["connector"]
        owners = CONNECTOR_OWNERS.get(connector, [])
        owner_str = " ".join(owners) if owners else "_(no owner mapped)_"
        detail_str = ", ".join(f"`{d}`" for d in entry.get("details", [])) if entry.get("details") else ""
        if detail_str:
            lines.append(f"• *{connector}* — {detail_str}\n  👉 {owner_str} — can you share status?")
        else:
            lines.append(f"• *{connector}*\n  👉 {owner_str} — can you share status?")

    result = slack_post(token, "chat.postMessage", {
        "channel": CHANNEL_ID,
        "thread_ts": msg_ts,
        "text": "\n".join(lines),
        "mrkdwn": True,
    })
    if result.get("ok"):
        print(f"✅ Posted next-day follow-up in thread {msg_ts}")
    else:
        print(f"❌ Failed to post: {result.get('error')}")
    return result.get("ok", False)


# ── Modes ─────────────────────────────────────────────────────────────────────

def mode_detect(token, state):
    """Hourly: detect new reports, post initial follow-up, save to pending."""
    last_ts = state.get("last_processed_ts", "0")
    print(f"Checking for new reports since ts={last_ts}")

    reports = get_recent_reports(token, since_ts=last_ts)
    print(f"Found {len(reports)} failure report(s)")

    latest_ts = last_ts
    pending = state.get("pending_followup", {})

    for report in reports:
        msg_ts = report["ts"]
        print(f"\nProcessing report ts={msg_ts}")

        if already_replied(token, msg_ts):
            print(f"  Already replied, skipping")
        else:
            failures = parse_failures(report.get("text", ""))
            print(f"  Failures: {[f['connector'] for f in failures]}")
            if failures:
                ok = post_followup(token, msg_ts, failures)
                if ok:
                    # Save to pending for next-day tracking
                    pending[msg_ts] = {
                        "failures": failures,
                        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                        "followed_up": False,
                    }

        if float(msg_ts) > float(latest_ts):
            latest_ts = msg_ts

    state["last_processed_ts"] = latest_ts
    state["pending_followup"] = pending
    save_state(state)
    print(f"\nState saved. Pending threads: {len(pending)}")


def mode_followup(token, state):
    """Daily morning: check yesterday's threads, post follow-up if no legit response."""
    pending = state.get("pending_followup", {})
    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    to_remove = []
    for msg_ts, entry in pending.items():
        report_date = entry.get("date", "")
        already_followed_up = entry.get("followed_up", False)

        # Only process yesterday's reports (not older, not today's)
        if report_date != yesterday:
            # Clean up old entries (>2 days)
            try:
                report_dt = datetime.strptime(report_date, "%Y-%m-%d")
                if (datetime.now() - report_dt).days > 2:
                    to_remove.append(msg_ts)
            except Exception:
                pass
            continue

        if already_followed_up:
            to_remove.append(msg_ts)
            continue

        print(f"\nChecking thread {msg_ts} (reported {report_date})")
        failures = entry.get("failures", [])

        # Gather all owner IDs for this set of failures
        all_owners = []
        for f in failures:
            all_owners.extend(CONNECTOR_OWNERS.get(f["connector"], []))
        all_owners = list(set(all_owners))

        if has_legit_response(token, msg_ts, all_owners):
            print(f"  Legit response found — no follow-up needed")
            entry["followed_up"] = True
        else:
            print(f"  No legit response — posting next-day follow-up")
            still_unresolved = failures  # could filter by connector if needed
            ok = post_nextday_followup(token, msg_ts, still_unresolved)
            if ok:
                entry["followed_up"] = True

    for ts in to_remove:
        del pending[ts]

    state["pending_followup"] = pending
    save_state(state)
    print(f"\nDone. Remaining pending: {len(pending)}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    token = keyring.get_password("hermes", "SLACK_BOT_TOKEN")
    if not token:
        print("ERROR: No SLACK_BOT_TOKEN in keyring")
        return

    state = load_state()
    mode = "--followup" in sys.argv

    if mode:
        print("=== MODE: Next-day follow-up check ===")
        mode_followup(token, state)
    else:
        print("=== MODE: Detect new reports ===")
        mode_detect(token, state)


if __name__ == "__main__":
    main()
