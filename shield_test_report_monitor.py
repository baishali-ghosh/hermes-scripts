"""
Shield Connector Test Report Monitor
=====================================
Monitors #ipe-shield-team for daily ISNotifications test reports.
When a report with failures is posted, replies in thread tagging connector owners.

State file: shield_test_report_state.json (same dir as script)
"""

import keyring
import requests
import json
import os
import re
from datetime import datetime, timezone

# ── Config ──────────────────────────────────────────────────────────────────
CHANNEL_ID = "C04QSSY4BNY"           # #ipe-shield-team
BOT_ID = "B08Q29GSER1"               # ISNotifications bot
STATE_FILE = os.path.join(os.path.dirname(__file__), "shield_test_report_state.json")

# Slack user IDs for Shield connector owners (confirmed in-channel)
OWNERS = {
    "sanjeet":  "U06CXP781G8",   # Sanjeet Manna
    "ojal":     "U094Q8LQJTA",   # Ojal Kumar
    "charan":   "U092M9RLQ4S",   # Charan Karpuram
    "mukund":   "U01SFJWTJPN",   # Mukund Bayyaram
    "rahul_k":  "U094KENF19P",   # Rahul Katikineni
    "shyam":    "U029Q2QG1A4",   # Shyam Gupta
    # Rohit not confirmed in channel — skip for now
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
    "uipath-google-cloudplatform":                   [uid("charan")],   # Rohit is owner, Charan fallback
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
    "uipath-microsoft-azureaifoundry":               [uid("charan")],  # Rohit is owner, fallback
}


def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {"last_processed_ts": "0"}


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def get_recent_reports(token, since_ts):
    """Fetch recent messages from channel, look for bot test reports."""
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(
        "https://slack.com/api/conversations.history",
        headers=headers,
        params={
            "channel": CHANNEL_ID,
            "oldest": since_ts,
            "limit": 10,
        }
    )
    data = resp.json()
    if not data.get("ok"):
        print(f"Error fetching history: {data.get('error')}")
        return []

    reports = []
    for msg in data.get("messages", []):
        # Must be from the ISNotifications bot
        if msg.get("bot_id") != BOT_ID:
            continue
        text = msg.get("text", "")
        # Must contain failure indicators
        if "🔴" not in text:
            continue
        reports.append(msg)
    return reports


def parse_failures(text):
    """
    Parse the report table and extract failed connectors.
    Returns list of dicts: {connector, failed_activities, failed_triggers}
    """
    failures = []
    lines = text.split("\n")
    for line in lines:
        if "🔴" not in line:
            continue
        # Extract connector name
        # Format: 🔴 uipath-xxxx-yyyy   N   N   N   [ACTIVITY]   [TRIGGER]
        connector_match = re.search(r'🔴\s+(uipath-[\w-]+)', line)
        if not connector_match:
            continue
        connector = connector_match.group(1).strip()

        # Extract failed activities
        acts_match = re.findall(r'\[([^\]]+)\]', line)
        activities = [a for a in acts_match if a.lower() != "none"]

        failures.append({
            "connector": connector,
            "details": activities,
        })
    return failures


def get_thread_replies(token, msg_ts):
    """Check if we've already replied to this thread."""
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(
        "https://slack.com/api/conversations.replies",
        headers=headers,
        params={"channel": CHANNEL_ID, "ts": msg_ts, "limit": 20}
    )
    data = resp.json()
    if not data.get("ok"):
        return []
    return data.get("messages", [])


def already_replied(token, msg_ts, our_bot_token_check=None):
    """Check if we already posted a follow-up in this thread."""
    replies = get_thread_replies(token, msg_ts)
    for reply in replies:
        # Check if any reply mentions connector owners (contains <@U...)
        text = reply.get("text", "")
        if "🚨 *Connector Failure Follow-up*" in text:
            return True
    return False


def post_followup(token, msg_ts, failures):
    """Post a reply in thread tagging owners for each failure."""
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    lines = ["🚨 *Connector Failure Follow-up* — please investigate and share status:\n"]

    for f in failures:
        connector = f["connector"]
        owners = CONNECTOR_OWNERS.get(connector, [])
        details = f["details"]

        owner_str = " ".join(owners) if owners else "_(no owner mapped)_"
        detail_str = ", ".join(f"`{d}`" for d in details) if details else ""

        if detail_str:
            lines.append(f"• *{connector}* — {detail_str}\n  👉 {owner_str}")
        else:
            lines.append(f"• *{connector}*\n  👉 {owner_str}")

    reply_text = "\n".join(lines)

    payload = {
        "channel": CHANNEL_ID,
        "thread_ts": msg_ts,
        "text": reply_text,
        "mrkdwn": True,
    }

    resp = requests.post("https://slack.com/api/chat.postMessage", headers=headers, json=payload)
    result = resp.json()
    if result.get("ok"):
        print(f"✅ Posted follow-up in thread {msg_ts}")
    else:
        print(f"❌ Failed to post: {result.get('error')}")
    return result.get("ok", False)


def main():
    token = keyring.get_password("hermes", "SLACK_BOT_TOKEN")
    if not token:
        print("ERROR: No SLACK_BOT_TOKEN in keyring")
        return

    state = load_state()
    last_ts = state.get("last_processed_ts", "0")
    print(f"Checking for reports since ts={last_ts}")

    reports = get_recent_reports(token, since_ts=last_ts)
    print(f"Found {len(reports)} failure report(s)")

    latest_ts = last_ts
    for report in reports:
        msg_ts = report["ts"]
        print(f"\nProcessing report ts={msg_ts}")

        if already_replied(token, msg_ts):
            print(f"  Already replied to {msg_ts}, skipping")
        else:
            failures = parse_failures(report.get("text", ""))
            print(f"  Failures: {[f['connector'] for f in failures]}")
            if failures:
                ok = post_followup(token, msg_ts, failures)
                if ok:
                    print(f"  Replied successfully")
            else:
                print(f"  No parseable failures found")

        if float(msg_ts) > float(latest_ts):
            latest_ts = msg_ts

    # Update state to avoid re-processing
    state["last_processed_ts"] = latest_ts
    save_state(state)
    print(f"\nState updated: last_processed_ts={latest_ts}")


if __name__ == "__main__":
    main()
