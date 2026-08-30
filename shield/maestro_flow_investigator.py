"""
maestro_flow_investigator.py
============================
Spawns a Claude Code session to investigate a Shield-owned #help-maestro-flow
issue against the relevant local codebases.

If a fix is identified, creates a Jira ticket (ENGCE, Shield board 2456)
with the suggested fix, file path(s), and evidence.

Called from maestro_flow_triage.py after classify_with_llm() returns owner=Shield.

Returns a dict:
  {
    "investigated": True/False,
    "fix_found": True/False,
    "summary": "<1-3 sentence findings>",
    "fix_description": "<what to change and where>",    # only if fix_found
    "files": ["repo::path::Lstart-Lend", ...],         # only if fix_found
    "jira_key": "ENGCE-XXXXX",                         # only if ticket created
    "jira_url": "https://...",                          # only if ticket created
    "error": "<error message if investigation failed>", # only on failure
  }
"""

import os, sys, json, re, subprocess, textwrap, keyring, requests, shutil
from dotenv import load_dotenv

load_dotenv(r"C:\Users\Baishali.Ghosh\AppData\Local\hermes\.env")

# ── Config ─────────────────────────────────────────────────────────────────────
CLAUDE_BIN = shutil.which("claude") or ""   # resolves correctly on Windows (.EXE)

# Local repo roots — used to give Claude Code relevant working directories
REPO_ROOTS = {
    "IntegrationServiceActivities": r"C:\Users\Baishali.Ghosh\source\repos\UiPath\IntegrationServiceActivities",
    "StudioWeb":                    r"C:\Users\Baishali.Ghosh\source\repos\UiPath\StudioWeb",
    "API-Workflow":                 r"C:\Users\Baishali.Ghosh\source\repos\UiPath\udon",
}

# Timeout for Claude Code investigation (seconds) — codebase search takes 60-90s
CLAUDE_TIMEOUT = 240

# Jira config
JIRA_BASE      = "https://uipath.atlassian.net"
JIRA_EMAIL     = "baishali.ghosh@uipath.com"
JIRA_PROJECT   = "ENGCE"
JIRA_BOARD     = 2456
SHIELD_LABEL   = "Shield"
BAISHALI_ID    = "61289a45fc550900711d5544"

# Active sprint (S199) — fetched dynamically
_active_sprint_id_cache: int = 0


# ── Jira helpers ───────────────────────────────────────────────────────────────
def _jira_token() -> str:
    return keyring.get_password("hermes", "JIRA_API_TOKEN") or ""


def _jira_headers() -> dict:
    import base64
    token = _jira_token()
    creds = base64.b64encode(f"{JIRA_EMAIL}:{token}".encode()).decode()
    return {
        "Authorization": f"Basic {creds}",
        "Content-Type":  "application/json",
        "Accept":        "application/json",
    }


def _get_active_sprint_id() -> int:
    global _active_sprint_id_cache
    if _active_sprint_id_cache:
        return _active_sprint_id_cache
    try:
        r = requests.get(
            f"{JIRA_BASE}/rest/agile/1.0/board/{JIRA_BOARD}/sprint",
            headers=_jira_headers(),
            params={"state": "active"},
            timeout=15,
        )
        for sprint in r.json().get("values", []):
            if "Shield" in sprint.get("name", ""):
                _active_sprint_id_cache = sprint["id"]
                return sprint["id"]
    except Exception as e:
        print(f"  [Jira] Sprint fetch error: {e}")
    return 0


def create_jira_ticket(summary: str, description: str) -> tuple[str, str]:
    """
    Creates a Jira ticket in ENGCE, assigned to Baishali, active Shield sprint.
    Returns (issue_key, issue_url) or ("", "") on failure.
    """
    sprint_id = _get_active_sprint_id()
    payload = {
        "fields": {
            "project":        {"key": JIRA_PROJECT},
            "summary":        summary,
            "description": {
                "type":    "doc",
                "version": 1,
                "content": [{
                    "type":    "paragraph",
                    "content": [{"type": "text", "text": description}]
                }]
            },
            "issuetype":      {"name": "Bug"},
            "assignee":       {"id": BAISHALI_ID},
            "labels":         [SHIELD_LABEL],
            **({"customfield_10006": sprint_id} if sprint_id else {}),
        }
    }
    try:
        r = requests.post(
            f"{JIRA_BASE}/rest/api/3/issue",
            headers=_jira_headers(),
            json=payload,
            timeout=20,
        )
        d = r.json()
        if r.ok and "key" in d:
            key = d["key"]
            url = f"{JIRA_BASE}/browse/{key}"
            print(f"  [Jira] Created {key}: {url}")
            return key, url
        print(f"  [Jira] Create failed: {r.status_code} {d}")
    except Exception as e:
        print(f"  [Jira] Exception: {e}")
    return "", ""


# ── Claude Code investigator ───────────────────────────────────────────────────
def _pick_workdir(routing: str) -> str:
    """
    Choose the best local repo root for Claude Code to work in,
    based on the routing path identified by the triage classifier.
    Falls back to ISA if uncertain.
    """
    r = routing.lower()
    if "studioweb" in r or "mfe" in r or "case" in r or "process" in r or "api workflow" in r:
        d = REPO_ROOTS["StudioWeb"]
    elif "api-workflow" in r or "udon" in r or "runtime" in r:
        d = REPO_ROOTS["API-Workflow"]
    else:
        d = REPO_ROOTS["IntegrationServiceActivities"]  # default for DAP/connector work
    return d if os.path.isdir(d) else REPO_ROOTS["IntegrationServiceActivities"]


def _build_investigation_prompt(thread_text: str, reporter: str,
                                 reasoning: str, routing_hint: str) -> str:
    return textwrap.dedent(f"""
    You are investigating a #help-maestro-flow Shield IS bug report.
    Triage routing: {reasoning}

    Bug report:
    {thread_text[:2000]}

    Tasks (in order, stop when done):
    1. Search for the most relevant code paths based on the routing hint: {routing_hint}
    2. Look for the specific field, function, or logic that would cause this symptom
    3. If you find a concrete bug (wrong value, missing null check, bad condition): describe the fix precisely
    4. If not found in 10 tool calls: stop and say so

    Respond with JSON only (no markdown):
    {{"fix_found": true|false, "summary": "...", "fix_description": "...", "files": ["path#L10-L20"]}}
    fix_found=true only if you are highly confident in the root cause AND have a concrete change.
    """).strip()


def run_investigation(thread_text: str, reporter: str,
                      reasoning: str, routing_hint: str) -> dict:
    """
    Spawns a Claude Code session (`claude -p`) in the relevant repo directory.
    Returns investigation result dict.
    """
    if not CLAUDE_BIN:
        return {"investigated": False, "fix_found": False,
                "error": "claude binary not found in PATH"}

    workdir = _pick_workdir(routing_hint)
    prompt  = _build_investigation_prompt(thread_text, reporter, reasoning, routing_hint)

    print(f"  [Investigator] Spawning Claude Code in: {workdir}")
    try:
        result = subprocess.run(
            [CLAUDE_BIN, "-p", "--max-turns", "15", "--output-format", "text"],
            input=prompt,
            cwd=workdir,
            capture_output=True,
            text=True,
            timeout=CLAUDE_TIMEOUT,
        )
        raw = result.stdout.strip()
        stderr = result.stderr.strip()

        if result.returncode != 0:
            print(f"  [Investigator] claude exited {result.returncode}: {stderr[:300]}")
            return {"investigated": True, "fix_found": False,
                    "summary": f"Investigation failed (exit {result.returncode}): {stderr[:200]}",
                    "error": stderr[:300]}

        # Strip markdown fences
        raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.MULTILINE)
        raw = re.sub(r"\s*```$", "", raw, flags=re.MULTILINE)

        # Find JSON block (Claude may print preamble text before the JSON)
        json_match = re.search(r"\{[\s\S]*\}", raw)
        if not json_match:
            print(f"  [Investigator] No JSON in response: {raw[:300]}")
            return {"investigated": True, "fix_found": False,
                    "summary": "Claude Code returned unstructured output — needs manual review.",
                    "raw_output": raw[:500]}

        data = json.loads(json_match.group(0))
        data["investigated"] = True
        print(f"  [Investigator] fix_found={data.get('fix_found')} | {data.get('summary','')[:80]}")
        return data

    except subprocess.TimeoutExpired:
        print(f"  [Investigator] Timed out after {CLAUDE_TIMEOUT}s")
        return {"investigated": True, "fix_found": False,
                "summary": f"Investigation timed out after {CLAUDE_TIMEOUT}s — thread may need more repro info.",
                "error": "timeout"}
    except json.JSONDecodeError as e:
        return {"investigated": True, "fix_found": False,
                "summary": "Claude Code output could not be parsed as JSON.",
                "error": str(e), "raw_output": raw[:500]}
    except Exception as e:
        print(f"  [Investigator] Unexpected error: {e}")
        return {"investigated": True, "fix_found": False,
                "summary": f"Investigation error: {e}", "error": str(e)}


# ── Main entry point ───────────────────────────────────────────────────────────
def investigate_and_file(thread_text: str, reporter: str, reasoning: str,
                          routing_hint: str, thread_url: str) -> dict:
    """
    Full pipeline:
      1. Spawn Claude Code → get findings
      2. If fix found → create Jira ticket
      3. Return enriched result dict

    thread_url: used in Jira description for traceability.
    """
    result = run_investigation(thread_text, reporter, reasoning, routing_hint)

    if result.get("fix_found"):
        fix_desc  = result.get("fix_description", "")
        summary   = result.get("summary", "")
        files     = result.get("files", [])
        files_str = "\n".join(f"  - {f}" for f in files) if files else "  (no specific file identified)"

        jira_summary = f"[Shield] {summary[:120]}"
        jira_desc    = (
            f"Identified via automated triage from #help-maestro-flow.\n\n"
            f"Slack thread: {thread_url}\n"
            f"Reporter: {reporter}\n\n"
            f"Triage reasoning: {reasoning}\n\n"
            f"--- Suggested Fix ---\n{fix_desc}\n\n"
            f"--- Relevant Files ---\n{files_str}\n\n"
            f"--- Investigation Summary ---\n{summary}"
        )

        key, url = create_jira_ticket(jira_summary, jira_desc)
        result["jira_key"] = key
        result["jira_url"] = url

    return result
