"""
shield_deprecation_tracker.py

Scans vendor API changelog/deprecation pages for Shield connectors.
Focuses specifically on API endpoint/version deprecations with dates.
- Posts clean inline alert to #is-shield-notifications
- Uploads a markdown report file to the channel
- Tags connector owners on Slack for upcoming deprecations (within 6 months)
"""

import json
import re
import time
import hashlib
import keyring
import requests
import tempfile
import os
from datetime import datetime, timezone
from pathlib import Path
from dateutil import parser as dateutil_parser

# ── Config ───────────────────────────────────────────────────────────────────
SLACK_CHANNEL = "C05161K9RSN"   # #is-shield-notifications
STATE_FILE    = Path(__file__).parent / "shield_deprecation_state.json"

HEADERS_WEB = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# ── Connector → Owner Slack ID map ───────────────────────────────────────────
# Based on Shield Connectors & Owner canvas (Jun 2026)
OWNER_IDS = {
    "Charan":  "U092M9RLQ4S",
    "Rahul":   "U094KENF19P",
    "Sanjeet": "U06CXP781G8",
    "Ojal":    "U094Q8LQJTA",
    "Rohit":   "U0A4AHF1XHS",
    "Mukund":  "U01SFJWTJPN",
    "Shyam":   "U029Q2QG1A4",
}

CONNECTOR_OWNERS = {
    "uipath-openai-openai":                      ["Charan", "Rahul"],
    "uipath-microsoft-azureopenai":              ["Ojal"],
    "uipath-anthropic-claude":                   ["Rohit"],
    "uipath-aws-bedrock":                        ["Charan"],
    "uipath-google-vertex":                      ["Sanjeet", "Rahul"],
    "uipath-ibm-watsonx":                        ["Rahul"],
    "uipath-amazon-sagemaker":                   ["Charan"],
    "uipath-openai-openaiv1compliant":           ["Ojal"],
    "uipath-deepseek-deepseek":                  ["Charan"],
    "uipath-nvidia-nim":                         ["Sanjeet"],
    "uipath-pinecone-pinecone":                  ["Charan"],
    "uipath-jina-jina":                          ["Ojal"],
    "uipath-perplexity-perplexity":              ["Charan"],
    "uipath-snowflake-snowflake":                ["Mukund", "Ojal", "Charan"],
    "uipath-snowflake-cortex":                   ["Sanjeet"],
    "uipath-databricks-databricks":              ["Ojal", "Charan"],
    "uipath-uipath-jdbc":                        ["Charan"],
    "uipath-amazon-webservices":                 ["Charan", "Rohit"],
    "uipath-google-cloudplatform":               ["Rohit"],
    "uipath-microsoft-azure":                    ["Sanjeet"],
    "uipath-microsoft-azureactivedirectory":     ["Sanjeet", "Rohit"],
    "uipath-datadog-datadog":                    ["Charan", "Sanjeet"],
    "uipath-salesforce-slack":                   ["Mukund", "Sanjeet"],
    "uipath-microsoft-github":                   ["Charan", "Rahul"],
    "uipath-box-box":                            ["Ojal", "Rahul"],
    "uipath-microsoft-powerautomate":            ["Rahul"],
    "uipath-microsoft-exchangeserver":           ["Rahul"],
    "uipath-google-vision":                      ["Rahul"],
    "uipath-microsoft-azureformrecognizer":      ["Sanjeet"],
    "uipath-microsoft-vision":                   ["Sanjeet"],
    "uipath-microsoft-azureaifoundry":           ["Rohit"],
    "uipath-microsoft-translator":               ["Ojal"],
    "uipath-microsoft-sentiment":                ["Rahul"],
    "uipath-microsoft-azureapplicationinsights": ["Sanjeet"],
    "uipath-microsoft-systemcenter":             ["Sanjeet"],
    "uipath-vmware-vsphere":                     ["Ojal"],
    "uipath-citrix-hypervisor":                  ["Rahul"],
    "uipath-google-agent2agent":                 ["Sanjeet", "Rahul"],
    "uipath-sap-odata":                          ["Shyam"],
    "uipath-microsoft-activedirectorydomainservices": ["Sanjeet"],
    "uipath-microsoft-hyperv":                   ["Rahul"],
}

UPCOMING_WINDOW_DAYS = 180  # 6 months

# ── API deprecation patterns ──────────────────────────────────────────────────
# Each pattern is a regex that must match near an API/endpoint/version signal.
# We require BOTH a deprecation signal AND an API signal in the same 600-char window.

DEPRECATION_SIGNALS = [
    r"will be deprecated",
    r"is deprecated",
    r"has been deprecated",
    r"deprecating",
    r"deprecation date",
    r"end.of.life",
    r"will be retired",
    r"is being retired",
    r"retirement date",
    r"will be removed",
    r"sunset date",
    r"sunsetting",
    r"no longer (be )?supported",
    r"support ends",
    r"support will end",
]

API_SIGNALS = [
    r"/v\d+",           # versioned endpoints like /v1, /v2
    r"api version",
    r"endpoint",
    r"model",           # model deprecations (LLM connectors)
    r"api key",
    r"legacy api",
    r"rest api",
    r"graphql",
    r"sdk",
    r"client library",
]

# Regex to extract a date from a snippet (various formats)
DATE_PATTERNS = [
    r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+20\d\d\b",
    r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\.?\s+\d{1,2},?\s+20\d\d\b",
    r"\b20\d\d-\d{2}-\d{2}\b",
    r"\bQ[1-4]\s*20\d\d\b",
    r"\b20\d\d\b",
]

# ── Connector list ────────────────────────────────────────────────────────────
CONNECTORS = [
    {"key": "uipath-openai-openai",           "vendor": "OpenAI",
     "urls": ["https://platform.openai.com/docs/deprecations"]},

    {"key": "uipath-microsoft-azureopenai",   "vendor": "Azure OpenAI",
     "urls": ["https://learn.microsoft.com/en-us/azure/ai-services/openai/api-version-deprecation"]},

    {"key": "uipath-anthropic-claude",        "vendor": "Anthropic Claude",
     "urls": ["https://docs.anthropic.com/en/docs/about-claude/models",
              "https://docs.anthropic.com/en/release-notes/api"]},

    {"key": "uipath-aws-bedrock",             "vendor": "AWS Bedrock",
     "urls": ["https://docs.aws.amazon.com/bedrock/latest/userguide/model-lifecycle.html"]},

    {"key": "uipath-google-vertex",           "vendor": "Google Vertex AI",
     "urls": ["https://cloud.google.com/vertex-ai/generative-ai/docs/deprecations"]},

    {"key": "uipath-ibm-watsonx",             "vendor": "IBM WatsonX",
     "urls": ["https://cloud.ibm.com/docs/watson?topic=watson-release-notes"]},

    {"key": "uipath-amazon-sagemaker",        "vendor": "AWS SageMaker",
     "urls": ["https://docs.aws.amazon.com/sagemaker/latest/dg/whats-new.html"]},

    {"key": "uipath-openai-openaiv1compliant","vendor": "OpenAI v1 Compliant",
     "urls": ["https://platform.openai.com/docs/deprecations"]},

    {"key": "uipath-deepseek-deepseek",       "vendor": "DeepSeek",
     "urls": ["https://api-docs.deepseek.com/news/news1120"]},

    {"key": "uipath-nvidia-nim",              "vendor": "NVIDIA NIM",
     "urls": ["https://docs.nvidia.com/nim/large-language-models/latest/release-notes.html"]},

    {"key": "uipath-pinecone-pinecone",       "vendor": "Pinecone",
     "urls": ["https://docs.pinecone.io/changelog"]},

    {"key": "uipath-jina-jina",               "vendor": "Jina AI",
     "urls": ["https://jina.ai/changelog"]},

    {"key": "uipath-perplexity-perplexity",   "vendor": "Perplexity",
     "urls": ["https://docs.perplexity.ai/changelog"]},

    {"key": "uipath-snowflake-snowflake",     "vendor": "Snowflake",
     "urls": ["https://docs.snowflake.com/en/release-notes/bcr-bundles/overview"]},

    {"key": "uipath-snowflake-cortex",        "vendor": "Snowflake Cortex",
     "urls": ["https://docs.snowflake.com/en/release-notes/bcr-bundles/overview"]},

    {"key": "uipath-databricks-databricks",   "vendor": "Databricks",
     "urls": ["https://docs.databricks.com/en/release-notes/api.html"]},

    {"key": "uipath-amazon-webservices",      "vendor": "AWS",
     "urls": ["https://aws.amazon.com/releasenotes/"]},

    {"key": "uipath-google-cloudplatform",    "vendor": "Google Cloud",
     "urls": ["https://cloud.google.com/release-notes"]},

    {"key": "uipath-microsoft-azure",         "vendor": "Microsoft Azure",
     "urls": ["https://azure.microsoft.com/en-us/updates/?updateType=retirements"]},

    {"key": "uipath-microsoft-azureactivedirectory", "vendor": "Azure Active Directory",
     "urls": ["https://learn.microsoft.com/en-us/entra/identity/deprecations"]},

    {"key": "uipath-datadog-datadog",         "vendor": "Datadog",
     "urls": ["https://docs.datadoghq.com/agent/versions/upgrade_to_agent_v7/"]},

    {"key": "uipath-salesforce-slack",        "vendor": "Slack",
     "urls": ["https://api.slack.com/deprecations"]},

    {"key": "uipath-microsoft-github",        "vendor": "GitHub",
     "urls": ["https://docs.github.com/en/rest/overview/breaking-changes"]},

    {"key": "uipath-box-box",                 "vendor": "Box",
     "urls": ["https://developer.box.com/changelog/"]},

    {"key": "uipath-microsoft-powerautomate", "vendor": "Power Automate",
     "urls": ["https://learn.microsoft.com/en-us/power-automate/whats-new"]},

    {"key": "uipath-microsoft-exchangeserver","vendor": "Exchange Server",
     "urls": ["https://learn.microsoft.com/en-us/exchange/new-features/new-features"]},

    {"key": "uipath-google-vision",           "vendor": "Google Vision API",
     "urls": ["https://cloud.google.com/vision/docs/release-notes"]},

    {"key": "uipath-microsoft-azureformrecognizer","vendor": "Azure Form Recognizer / Doc Intelligence",
     "urls": ["https://learn.microsoft.com/en-us/azure/ai-services/document-intelligence/whats-new"]},

    {"key": "uipath-microsoft-vision",        "vendor": "Microsoft Computer Vision",
     "urls": ["https://learn.microsoft.com/en-us/azure/ai-services/computer-vision/whats-new"]},

    {"key": "uipath-microsoft-azureaifoundry","vendor": "Azure AI Foundry",
     "urls": ["https://learn.microsoft.com/en-us/azure/ai-studio/whats-new"]},

    {"key": "uipath-microsoft-translator",    "vendor": "Microsoft Translator",
     "urls": ["https://learn.microsoft.com/en-us/azure/ai-services/translator/whats-new"]},

    {"key": "uipath-microsoft-sentiment",     "vendor": "Azure Text Analytics",
     "urls": ["https://learn.microsoft.com/en-us/azure/ai-services/language-service/whats-new"]},

    {"key": "uipath-microsoft-azureapplicationinsights", "vendor": "Azure Application Insights",
     "urls": ["https://learn.microsoft.com/en-us/azure/azure-monitor/app/release-notes"]},

    {"key": "uipath-microsoft-systemcenter",  "vendor": "SCOM / System Center",
     "urls": ["https://learn.microsoft.com/en-us/system-center/scom/release-notes-scom"]},

    {"key": "uipath-vmware-vsphere",          "vendor": "VMware vSphere",
     "urls": ["https://docs.vmware.com/en/VMware-vSphere/index.html"]},

    {"key": "uipath-citrix-hypervisor",       "vendor": "Citrix Hypervisor",
     "urls": ["https://docs.xenserver.com/en-us/citrix-hypervisor/whats-new.html"]},

    {"key": "uipath-google-agent2agent",      "vendor": "Google Agent2Agent",
     "urls": ["https://cloud.google.com/vertex-ai/generative-ai/docs/deprecations"]},

    {"key": "uipath-sap-odata",               "vendor": "SAP OData",
     "urls": ["https://api.sap.com/news"]},
]


# ── Helpers ───────────────────────────────────────────────────────────────────

def load_state():
    if STATE_FILE.exists():
        with open(STATE_FILE) as f:
            return json.load(f)
    return {"seen": {}}


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def fetch_page(url, timeout=15):
    try:
        r = requests.get(url, headers=HEADERS_WEB, timeout=timeout)
        if r.status_code == 200:
            return r.text
    except Exception:
        pass
    return ""


def strip_html(html):
    text = re.sub(r'<style[^>]*>.*?</style>', ' ', html, flags=re.DOTALL)
    text = re.sub(r'<script[^>]*>.*?</script>', ' ', text, flags=re.DOTALL)
    text = re.sub(r'<[^>]+>', ' ', text)
    for ent, rep in [('&amp;','&'),('&lt;','<'),('&gt;','>'),('&nbsp;',' '),('&#39;',"'"),('&quot;','"')]:
        text = text.replace(ent, rep)
    return re.sub(r'\s+', ' ', text).strip()


def extract_date(text):
    """Try to extract a deprecation date from a text snippet."""
    for pat in DATE_PATTERNS:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            return m.group(0)
    return "Date not specified"


def extract_api_name(snippet):
    """Try to extract the API/endpoint/model name from a snippet."""
    ISO_DATE = re.compile(r'^\d{4}-\d{2}-\d{2}$')

    patterns = [
        r'(gpt-[a-z0-9][a-z0-9.-]{2,40})',          # GPT model names
        r'(claude-[a-z0-9][a-z0-9.-]{2,40})',        # Claude model names
        r'(gemini-[a-z0-9][a-z0-9.-]{2,40})',        # Gemini model names
        r'(mistral-[a-z0-9][a-z0-9.-]{2,40})',       # Mistral model names
        r'(llama-[a-z0-9][a-z0-9.-]{2,40})',         # Llama model names
        r'(titan-[a-z0-9][a-z0-9.-]{2,40})',         # AWS Titan models
        r'((?:GET|POST|PUT|DELETE|PATCH)\s+/\S+)',   # HTTP method + path
        r'(API\s+version\s+[\d\-]+)',                 # "API version 2024-02-01"
        r'(v\d+(?:\.\d+)*\s+API)',                   # "v2.0 API"
        r'(/api/v\d+[/\w-]{0,40})',                  # /api/v1/... paths
        r'`([a-zA-Z0-9][^`]{4,60})`',               # backtick-quoted (min 5 chars)
        r'"([a-zA-Z][^"]{4,60})"',                   # double-quoted (must start with letter)
    ]
    for pat in patterns:
        m = re.search(pat, snippet, re.IGNORECASE)
        if m:
            val = m.group(1).strip()
            if ISO_DATE.match(val):
                continue
            if re.match(r'^\d+$', val):
                continue
            if len(val) < 4:
                continue
            return val
    return None


def find_api_deprecations(text, connector_key, url):
    """
    Find snippets that contain BOTH a deprecation signal AND an API signal
    within a 600-char window. Returns list of structured hits.
    """
    hits = []
    seen_buckets = set()

    dep_compiled = [re.compile(p, re.IGNORECASE) for p in DEPRECATION_SIGNALS]
    api_compiled = [re.compile(p, re.IGNORECASE) for p in API_SIGNALS]

    # Scan with a sliding window
    window = 600
    step   = 150
    length = len(text)

    for pos in range(0, length - window, step):
        chunk = text[pos: pos + window]

        has_dep = any(p.search(chunk) for p in dep_compiled)
        if not has_dep:
            continue
        has_api = any(p.search(chunk) for p in api_compiled)
        if not has_api:
            continue

        # Deduplicate overlapping windows
        bucket = pos // 300
        if bucket in seen_buckets:
            continue
        seen_buckets.add(bucket)

        # Find the specific deprecation signal that triggered
        trigger_kw = next((p.pattern for p in dep_compiled if p.search(chunk)), "deprecated")

        snippet  = re.sub(r'\s+', ' ', chunk).strip()
        api_name = extract_api_name(snippet)
        date     = extract_date(snippet)
        hit_hash = hashlib.md5(f"{connector_key}:{url}:{snippet[:120]}".encode()).hexdigest()[:12]

        # Only surface hits where we can identify both the API name AND a date
        if not api_name or date == "Date not specified":
            continue

        hits.append({
            "hash":     hit_hash,
            "api_name": api_name,
            "date":     date,
            "trigger":  trigger_kw,
            "snippet":  snippet[:400],
            "url":      url,
        })

    return hits


def post_slack(token, channel, text):
    r = requests.post(
        "https://slack.com/api/chat.postMessage",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={"channel": channel, "text": text, "mrkdwn": True},
        timeout=15,
    )
    return r.json()


def upload_file_to_slack(token, channel, filename, content, title):
    """Upload a text file to a Slack channel using files.getUploadURLExternal."""
    try:
        encoded = content.encode("utf-8")
        # Step 1: get upload URL — must use form-encoded params not JSON
        r1 = requests.post(
            "https://slack.com/api/files.getUploadURLExternal",
            headers={"Authorization": f"Bearer {token}"},
            data={"filename": filename, "length": len(encoded)},
            timeout=15,
        )
        d1 = r1.json()
        if not d1.get("ok"):
            return None, d1.get("error")

        upload_url = d1["upload_url"]
        file_id    = d1["file_id"]

        # Step 2: upload content
        requests.post(upload_url,
            headers={"Content-Type": "application/octet-stream"},
            data=encoded, timeout=30)

        # Step 3: complete upload and share to channel
        r3 = requests.post(
            "https://slack.com/api/files.completeUploadExternal",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={"files": [{"id": file_id, "title": title}], "channel_id": channel},
            timeout=15,
        )
        d3 = r3.json()
        return d3.get("ok"), d3.get("error")
    except Exception as e:
        return None, str(e)


def is_upcoming(date_str, window_days=UPCOMING_WINDOW_DAYS):
    """Returns True if the deprecation date is in the future and within window_days."""
    try:
        dt = dateutil_parser.parse(date_str, default=datetime(datetime.now().year, 1, 1))
        now = datetime.now()
        diff = (dt - now).days
        return 0 <= diff <= window_days
    except Exception:
        # If only a year is given (e.g. "2026"), treat as upcoming if it's this/next year
        year_match = re.search(r'\b(20\d\d)\b', date_str)
        if year_match:
            year = int(year_match.group(1))
            return datetime.now().year <= year <= datetime.now().year + 1
        return False


def owner_mentions(connector_key):
    """Returns a list of Slack <@uid> mention strings for a connector's owners."""
    owners = CONNECTOR_OWNERS.get(connector_key, [])
    return [f"<@{OWNER_IDS[o]}>" for o in owners if o in OWNER_IDS]


def build_markdown_report(today_str, by_connector, all_findings):
    """Build a clean markdown file for the report."""
    lines = [
        f"# 🔌 Shield Connector — API Deprecation Alerts",
        f"**Date:** {today_str}",
        f"**Connectors affected:** {len(by_connector)} | **Total deprecations:** {len(all_findings)}",
        "",
        "---",
        "",
    ]

    for connector_key, findings in by_connector.items():
        vendor = findings[0]["vendor"]
        owners = CONNECTOR_OWNERS.get(connector_key, [])
        lines.append(f"## {vendor} (`{connector_key}`)")
        if owners:
            lines.append(f"**Owners:** {', '.join(owners)}")
        lines.append("")

        # Deduplicate
        seen_in_block = set()
        deduped = []
        for f in findings:
            k = (f["api_name"], f["date"])
            if k not in seen_in_block:
                seen_in_block.add(k)
                deduped.append(f)

        lines.append("| API | Deprecation Date | Upcoming? |")
        lines.append("|-----|-----------------|-----------|")
        for f in deduped:
            upcoming = "⚠️ Yes" if is_upcoming(f["date"]) else "Historical"
            lines.append(f"| `{f['api_name']}` | {f['date']} | {upcoming} |")

        lines.append("")
        lines.append(f"Source: {findings[0]['url']}")
        lines.append("")
        lines.append("---")
        lines.append("")

    lines.append(f"*Generated by Shield Deprecation Tracker — runs every Monday 9 AM IST*")
    lines.append(f"*Next run: Mon {(datetime.now()).strftime('%d %b %Y')}*")
    return "\n".join(lines)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    slack_token = keyring.get_password("hermes", "SLACK_BOT_TOKEN")
    state = load_state()
    seen  = state.get("seen", {})

    new_findings = []
    CURRENT_YEAR = datetime.now().year
    MIN_YEAR     = CURRENT_YEAR - 1

    for connector in CONNECTORS:
        if not connector["urls"]:
            continue
        key    = connector["key"]
        vendor = connector["vendor"]

        for url in connector["urls"]:
            time.sleep(0.5)
            html = fetch_page(url)
            if not html:
                continue
            text = strip_html(html)
            hits = find_api_deprecations(text, key, url)

            for hit in hits:
                h = hit["hash"]
                if h not in seen:
                    # Silently seed historical ones
                    year_match = re.search(r'\b(20\d\d)\b', hit["date"])
                    if year_match and int(year_match.group(1)) < MIN_YEAR:
                        seen[h] = {"first_seen": "historical", "connector": key, "vendor": vendor, "url": url}
                        continue

                    seen[h] = {
                        "first_seen": datetime.now().strftime("%Y-%m-%d"),
                        "connector":  key,
                        "vendor":     vendor,
                        "url":        url,
                    }
                    new_findings.append({
                        "connector": key,
                        "vendor":    vendor,
                        **hit,
                    })

    save_state({"seen": seen})

    if not new_findings:
        print("")
        return

    # Group by connector
    by_connector = {}
    for f in new_findings:
        by_connector.setdefault(f["connector"], []).append(f)

    today_str = datetime.now().strftime("%d %b %Y")

    # ── 1. Inline Slack message ───────────────────────────────────────────────
    lines = [
        f"🔌 *Shield Connector — API Deprecation Alerts* | {today_str}",
        f"*{len(new_findings)} new API deprecation(s)* across *{len(by_connector)} connector(s)*",
        "─" * 40,
        "",
    ]

    for connector_key, findings in by_connector.items():
        vendor = findings[0]["vendor"]
        lines.append(f"*{vendor}*")

        seen_in_block = set()
        deduped = []
        for f in findings:
            k = (f["api_name"], f["date"])
            if k not in seen_in_block:
                seen_in_block.add(k)
                deduped.append(f)

        for f in deduped[:5]:
            upcoming_flag = " ⚠️ _upcoming_" if is_upcoming(f["date"]) else ""
            lines.append(f"  • *API:* `{f['api_name']}`")
            lines.append(f"    *Deprecation:* {f['date']}{upcoming_flag}")
            lines.append(f"    *Source:* <{f['url']}|view docs>")
        if len(deduped) > 5:
            lines.append(f"  _...and {len(deduped) - 5} more — see attached report_")
        lines.append("")

    lines.append("_Full details in the attached report. Owners tagged below for upcoming deprecations._")

    post_slack(slack_token, SLACK_CHANNEL, "\n".join(lines))

    # ── 2. Upload markdown report file ────────────────────────────────────────
    report_md   = build_markdown_report(today_str, by_connector, new_findings)
    report_name = f"shield_deprecation_{datetime.now().strftime('%d%b%Y').lower()}.md"
    ok, err = upload_file_to_slack(slack_token, SLACK_CHANNEL, report_name, report_md,
                                   f"Shield API Deprecation Report — {today_str}")
    if not ok:
        print(f"⚠️  File upload failed: {err}")

    # ── 3. Tag owners for upcoming deprecations ───────────────────────────────
    # Collect upcoming items grouped by owner
    owner_alerts = {}  # owner_name → list of (vendor, api_name, date)
    for f in new_findings:
        if not is_upcoming(f["date"]):
            continue
        owners = CONNECTOR_OWNERS.get(f["connector"], [])
        for owner in owners:
            owner_alerts.setdefault(owner, []).append(f)

    if owner_alerts:
        tag_lines = ["👋 *Owner heads-up — upcoming API deprecations needing attention:*", ""]
        for owner, items in owner_alerts.items():
            uid = OWNER_IDS.get(owner)
            if not uid:
                continue
            # Deduplicate by (connector, api, date)
            seen_items = set()
            deduped_items = []
            for f in items:
                k = (f["connector"], f["api_name"], f["date"])
                if k not in seen_items:
                    seen_items.add(k)
                    deduped_items.append(f)

            tag_lines.append(f"<@{uid}>")
            for f in deduped_items[:4]:
                tag_lines.append(f"  • *{f['vendor']}* — `{f['api_name']}` deprecating *{f['date']}*")
                tag_lines.append(f"    <{f['url']}|view docs>")
            if len(deduped_items) > 4:
                tag_lines.append(f"  _...and {len(deduped_items)-4} more in the report_")
            tag_lines.append("")

        post_slack(slack_token, SLACK_CHANNEL, "\n".join(tag_lines))

    total_upcoming = sum(1 for f in new_findings if is_upcoming(f["date"]))
    print(f"✅ Posted {len(new_findings)} deprecations ({total_upcoming} upcoming) | "
          f"file uploaded | {len(owner_alerts)} owner(s) tagged → #is-shield-notifications")


if __name__ == "__main__":
    main()
