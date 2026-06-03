# Shield Connector Deprecation Tracker

Monitors official vendor API/changelog pages for all Shield-owned connectors.
Detects API endpoint/model deprecations with dates and posts alerts to `#is-shield-notifications`.

## What it does
- Scrapes 40+ vendor deprecation/changelog pages weekly
- Surfaces only **new** deprecations with a named API and a date (no noise)
- Filters out historical deprecations (> 1 year old)
- Posts a clean inline summary to `#is-shield-notifications`
- Uploads a markdown report file to the channel
- Tags connector owners directly for any deprecations within the next 6 months

## Schedule
Runs every **Monday 9 AM IST** via Hermes cron (job `6d52446878a6`).

## Setup
1. Ensure `SLACK_BOT_TOKEN` is stored in Windows Credential Manager:
   ```python
   import keyring
   keyring.set_password("hermes", "SLACK_BOT_TOKEN", "xoxb-...")
   ```
2. Install dependencies:
   ```bash
   pip install requests python-dateutil
   ```
3. Copy `shield_deprecation_state.json.template` → `shield_deprecation_state.json` on first run.
   The script auto-seeds state on first run (all existing deprecations treated as known).

## State file
`shield_deprecation_state.json` — persists seen deprecation hashes so only new ones alert.
Not committed to git (gitignored). Template provided.

## Connectors covered
All 40+ Shield-owned connectors including:
OpenAI, Azure OpenAI, Anthropic Claude, AWS Bedrock, Google Vertex, IBM WatsonX,
Snowflake, Databricks, Datadog, Slack, GitHub, Box, Pinecone, Perplexity, DeepSeek,
NVIDIA NIM, Azure AD, Power Automate, Exchange Server, Google Vision, Azure Form Recognizer,
VMware vSphere, Citrix Hypervisor, SAP OData, and more.

## Output format (Slack)
Message 1 — Inline summary with ⚠️ flag on upcoming deprecations  
Message 2 — Markdown report file attachment  
Message 3 — Owner tags for deprecations within next 6 months  
