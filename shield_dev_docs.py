#!/usr/bin/env python3
"""
Shield Team — Per-Sprint Developer Productivity Docs
Generates one markdown doc per engineer per sprint.

Metrics:
  - Velocity (tickets done, story points)
  - Complexity score (repos touched, cross-service touchpoints)
  - Customer issue weighting (2x weight for customer-reported issues)
  - Objective ranking relative to peers in same role
  - Carry-over analysis

Usage:
  export JIRA_API_TOKEN="your_token"
  python shield_dev_docs.py
"""

import requests
import json
import os
import re
from datetime import datetime, timezone
from collections import defaultdict
from pathlib import Path

def _get_jira_token():
    """Load Jira token from Windows Credential Manager, fallback to env var."""
    try:
        import keyring
        token = keyring.get_password("hermes", "JIRA_API_TOKEN")
        if token:
            return token
    except Exception:
        pass
    return os.environ.get("JIRA_API_TOKEN", "")

# ── Config ────────────────────────────────────────────────────────────────────
JIRA_BASE   = "https://uipath.atlassian.net"
JIRA_USER   = "baishali.ghosh@uipath.com"
JIRA_TOKEN  = _get_jira_token()
BOARD_ID    = 2456
PROJECT_KEY = "ENGCE"
OUTPUT_DIR  = Path("C:/Users/Baishali.Ghosh/shield-team-docs")

auth    = (JIRA_USER, JIRA_TOKEN)
headers = {"Accept": "application/json"}

# ── Team: exclude Ben, Giri, Mukesh ──────────────────────────────────────────
TEAM = {
    "61289a45fc550900711d5544":                    {"name": "Baishali Ghosh", "role": "tech_lead"},
    "605b29ab14a23b0069cd3770":                    {"name": "Chandu",         "role": "engineer"},
    "712020:5948b4f2-a575-41e2-a76f-491f7b7b2cd4": {"name": "Charan",         "role": "engineer"},
    "712020:969c1cd2-6c4c-427d-bdea-27e7fd1f539e": {"name": "Rahul",          "role": "senior_engineer"},
    "712020:2bd5cd6a-334d-48b4-af0e-fec2da48758f": {"name": "Rohit",          "role": "engineer"},
    "712020:2f339e42-e0aa-4464-9dc6-e32d91a14956": {"name": "Sanjeet",        "role": "engineer"},
    "60face521c57770070d41ee5":                    {"name": "Shyam",          "role": "engineer"},
    "712020:89f83693-a619-42a5-a23f-0ea40c216456": {"name": "Ojal",           "role": "senior_engineer"},
    "712020:d69d76ae-ff5d-4560-abc4-f55632dfe736": {"name": "Pritish",        "role": "engineer"},
    "605b29ae570829006aead0a3":                    {"name": "Mukund",         "role": "senior_engineer"},
}

DONE_STATUSES     = {"Done", "Closed", "Resolved", "Merged"}
ACTIVE_STATUSES   = {"In Progress", "PR Review"}
BLOCKED_STATUSES  = {"Pending", "Open", "To Do"}

# Customer issue signals in summary/labels
CUSTOMER_KEYWORDS = ["customer", "bug", "prod issue", "regression", "escalation",
                     "hotfix", "sev", "critical", "p0", "p1"]

# Complexity: repos commonly touched per issue type
REPO_COMPLEXITY = {
    "connector":   3,
    "dap":         2,
    "rpa":         3,
    "runtime":     2,
    "flow":        2,
    "vscode":      2,
    "activity":    2,
    "managed http": 2,
    "jdbc":        2,
    "oauth":       2,
    "e2e":         3,
    "default":     1,
}

# ── API Helpers ───────────────────────────────────────────────────────────────
def get(url, params=None):
    r = requests.get(url, auth=auth, headers=headers, params=params, timeout=30)
    r.raise_for_status()
    return r.json()


def fetch_all_sprint_issues(sprint_id):
    """Fetch all issues in a sprint, paginating as needed."""
    issues = []
    start  = 0
    fields = ("summary,status,assignee,priority,issuetype,"
              "customfield_10016,labels,components,parent,created,updated")
    while True:
        data = get(
            f"{JIRA_BASE}/rest/agile/1.0/sprint/{sprint_id}/issue",
            params={"startAt": start, "maxResults": 50, "fields": fields},
        )
        batch = data.get("issues", [])
        issues.extend(batch)
        start += len(batch)
        if start >= data.get("total", 0) or not batch:
            break
    return issues


# ── Scoring ───────────────────────────────────────────────────────────────────
def is_customer_issue(issue):
    f       = issue["fields"]
    summary = (f.get("summary") or "").lower()
    labels  = [l.lower() for l in (f.get("labels") or [])]
    priority = (f.get("priority") or {}).get("name", "").lower()

    if any(k in summary for k in CUSTOMER_KEYWORDS):
        return True
    if any(k in labels for k in ["customer", "bug", "prod", "escalation"]):
        return True
    if priority in ("highest", "critical", "blocker"):
        return True
    return False


def estimate_complexity(issue):
    """Return a complexity score 1-5 based on area and touchpoints."""
    summary = (issue["fields"].get("summary") or "").lower()
    base = REPO_COMPLEXITY["default"]
    for keyword, score in REPO_COMPLEXITY.items():
        if keyword in summary:
            base = max(base, score)

    # Cross-component bonus
    components = issue["fields"].get("components") or []
    if len(components) > 1:
        base += 1

    # Has parent epic → more context needed
    if issue["fields"].get("parent"):
        base = min(base + 0.5, 5)

    return round(min(base, 5), 1)


def compute_weighted_score(done_issues):
    """
    Weighted productivity score:
      - Base: story points done (or 1 per ticket if no SP)
      - Complexity multiplier per ticket
      - Customer issue: 2x weight
    """
    score = 0
    for issue in done_issues:
        sp          = issue["fields"].get("customfield_10016") or 1
        complexity  = estimate_complexity(issue)
        customer_wt = 2.0 if is_customer_issue(issue) else 1.0
        score      += sp * complexity * customer_wt
    return round(score, 1)


# ── Per-engineer stats ────────────────────────────────────────────────────────
def build_engineer_stats(issues, account_id):
    mine = [i for i in issues
            if (i["fields"].get("assignee") or {}).get("accountId") == account_id]

    done       = [i for i in mine if i["fields"]["status"]["name"] in DONE_STATUSES]
    active     = [i for i in mine if i["fields"]["status"]["name"] in ACTIVE_STATUSES]
    blocked    = [i for i in mine if i["fields"]["status"]["name"] in BLOCKED_STATUSES]
    carry_over = [i for i in mine if i["fields"]["status"]["name"] not in DONE_STATUSES]

    sp_done    = sum(i["fields"].get("customfield_10016") or 0 for i in done)
    sp_total   = sum(i["fields"].get("customfield_10016") or 0 for i in mine)
    completion = round(len(done) / len(mine) * 100, 1) if mine else 0.0

    customer_done    = [i for i in done    if is_customer_issue(i)]
    customer_open    = [i for i in carry_over if is_customer_issue(i)]

    weighted = compute_weighted_score(done)

    return {
        "total":           len(mine),
        "done":            done,
        "active":          active,
        "blocked":         blocked,
        "carry_over":      carry_over,
        "sp_done":         sp_done,
        "sp_total":        sp_total,
        "completion_pct":  completion,
        "customer_done":   customer_done,
        "customer_open":   customer_open,
        "weighted_score":  weighted,
        "avg_complexity":  round(
            sum(estimate_complexity(i) for i in mine) / len(mine), 1
        ) if mine else 0.0,
    }


# ── Ranking within role ───────────────────────────────────────────────────────
def compute_rankings(all_stats):
    """Return dict of accountId → rank within same role."""
    by_role = defaultdict(list)
    for aid, info in all_stats.items():
        role = TEAM[aid]["role"]
        by_role[role].append((aid, info["weighted_score"]))

    rankings = {}
    for role, members in by_role.items():
        sorted_members = sorted(members, key=lambda x: x[1], reverse=True)
        for rank, (aid, _) in enumerate(sorted_members, 1):
            rankings[aid] = {"rank": rank, "of": len(sorted_members), "role": role}
    return rankings


# ── Markdown Doc Generator ────────────────────────────────────────────────────
def fmt_issue(issue):
    f       = issue["fields"]
    key     = issue["key"]
    summary = (f.get("summary") or "")[:80]
    status  = f["status"]["name"]
    sp      = f.get("customfield_10016")
    cust    = "🔴 Customer" if is_customer_issue(issue) else ""
    cmplx   = estimate_complexity(issue)
    sp_str  = f"SP:{int(sp)}" if sp else "SP:?"
    return f"- [{key}] {summary}  `{status}` `{sp_str}` `complexity:{cmplx}` {cust}"


def generate_doc(account_id, stats, rankings, sprint_name, sprint_start, sprint_end):
    info  = TEAM[account_id]
    name  = info["name"]
    role  = info["role"].replace("_", " ").title()
    rank  = rankings.get(account_id, {})
    rank_str = (f"#{rank['rank']} of {rank['of']} {rank['role'].replace('_',' ').title()}s"
                if rank else "N/A")

    lines = [
        f"# {name} — Sprint Deliverables",
        f"",
        f"**Sprint:** {sprint_name}",
        f"**Period:** {sprint_start} → {sprint_end}",
        f"**Role:** {role}",
        f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"",
        f"---",
        f"",
        f"## 📊 Sprint Summary",
        f"",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Total tickets assigned | {stats['total']} |",
        f"| ✅ Done | {len(stats['done'])} |",
        f"| 🔄 In Progress / PR Review | {len(stats['active'])} |",
        f"| ⏸ Blocked / Open | {len(stats['blocked'])} |",
        f"| 📦 Carry-overs | {len(stats['carry_over'])} |",
        f"| Story Points done / total | {stats['sp_done']} / {stats['sp_total']} |",
        f"| Completion % | {stats['completion_pct']}% |",
        f"| 🔴 Customer issues done | {len(stats['customer_done'])} |",
        f"| 🔴 Customer issues pending | {len(stats['customer_open'])} |",
        f"",
        f"---",
        f"",
        f"## 🏆 Productivity Score",
        f"",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Weighted score (complexity × SP × customer 2x) | **{stats['weighted_score']}** |",
        f"| Avg ticket complexity | {stats['avg_complexity']} / 5 |",
        f"| Team rank (within role) | **{rank_str}** |",
        f"",
        f"> **Scoring formula:** `story_points × complexity_score × customer_weight`  ",
        f"> Customer issues carry **2× weight**. Complexity is 1–5 based on repos/touchpoints.",
        f"",
        f"---",
        f"",
        f"## ✅ Completed This Sprint ({len(stats['done'])})",
        f"",
    ]

    if stats["done"]:
        # Customer issues first
        for i in sorted(stats["done"],
                        key=lambda x: (not is_customer_issue(x), -estimate_complexity(x))):
            lines.append(fmt_issue(i))
    else:
        lines.append("_No issues completed this sprint._")

    lines += [
        f"",
        f"---",
        f"",
        f"## 🔄 Carry-Overs ({len(stats['carry_over'])})",
        f"",
    ]

    if stats["carry_over"]:
        for i in sorted(stats["carry_over"],
                        key=lambda x: (not is_customer_issue(x),
                                       {"PR Review": 0, "In Progress": 1,
                                        "Pending": 2, "Open": 3, "To Do": 4}.get(
                                           x["fields"]["status"]["name"], 5))):
            lines.append(fmt_issue(i))
    else:
        lines.append("_No carry-overs. 🎉_")

    lines += [
        f"",
        f"---",
        f"",
        f"## 🔴 Customer Issues ({len(stats['customer_done']) + len(stats['customer_open'])} total)",
        f"",
        f"**Done ({len(stats['customer_done'])}):**",
    ]
    for i in stats["customer_done"]:
        lines.append(fmt_issue(i))
    if not stats["customer_done"]:
        lines.append("_None_")

    lines += [f"", f"**Pending ({len(stats['customer_open'])}):**"]
    for i in stats["customer_open"]:
        lines.append(fmt_issue(i))
    if not stats["customer_open"]:
        lines.append("_None_")

    lines.append("")
    return "\n".join(lines)


# ── Index doc ─────────────────────────────────────────────────────────────────
def generate_index(sprint_name, sprint_start, sprint_end, all_stats, rankings):
    rows = []
    for aid in sorted(all_stats, key=lambda x: -all_stats[x]["weighted_score"]):
        s    = all_stats[aid]
        name = TEAM[aid]["name"]
        role = TEAM[aid]["role"].replace("_", " ").title()
        rank = rankings.get(aid, {})
        rank_str = f"#{rank['rank']}/{rank['of']}" if rank else "-"
        rows.append(
            f"| {name} | {role} | {len(s['done'])}/{s['total']} | "
            f"{s['sp_done']}/{s['sp_total']} | {s['completion_pct']}% | "
            f"{s['weighted_score']} | {len(s['customer_done'])}/{len(s['customer_done'])+len(s['customer_open'])} | "
            f"{rank_str} |"
        )

    lines = [
        f"# Shield Team Sprint Docs — {sprint_name}",
        f"",
        f"**Period:** {sprint_start} → {sprint_end}  ",
        f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"",
        f"---",
        f"",
        f"## Team Overview",
        f"",
        f"| Engineer | Role | Done/Total | SP Done/Total | Completion | Weighted Score | Customer Issues | Rank |",
        f"|----------|------|-----------|--------------|------------|----------------|----------------|------|",
    ] + rows + [
        f"",
        f"> Weighted score = story_points × complexity (1–5) × customer_weight (2x for customer issues)",
        f"> Rank is relative within same role group.",
        f"",
        f"---",
        f"",
        f"## Individual Reports",
        f"",
    ]

    for aid in sorted(all_stats, key=lambda x: TEAM[x]["name"]):
        name     = TEAM[aid]["name"]
        filename = name.lower().replace(" ", "_") + ".md"
        lines.append(f"- [{name}](members/{filename})")

    lines.append("")
    return "\n".join(lines)


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    if not JIRA_TOKEN:
        print("❌ JIRA_API_TOKEN not set. Export it and re-run.")
        return

    print("🔍 Fetching active sprint...")
    sprint_data = get(
        f"{JIRA_BASE}/rest/agile/1.0/board/{BOARD_ID}/sprint",
        params={"state": "active"},
    )
    sprints = [s for s in sprint_data.get("values", [])
               if "shield" in s.get("name", "").lower()]
    if not sprints:
        print("❌ No active Shield sprint found.")
        return

    sprint      = sprints[0]
    sprint_id   = sprint["id"]
    sprint_name = sprint["name"]
    sprint_start = sprint.get("startDate", "")[:10]
    sprint_end   = sprint.get("endDate", "")[:10]
    print(f"✅ Sprint: {sprint_name} (id={sprint_id})")

    print("📥 Fetching all sprint issues...")
    issues = fetch_all_sprint_issues(sprint_id)
    print(f"   {len(issues)} issues fetched")

    # Build stats for each team member
    all_stats = {}
    for aid in TEAM:
        all_stats[aid] = build_engineer_stats(issues, aid)

    rankings = compute_rankings(all_stats)

    # Output dir
    sprint_slug = sprint_name.lower().replace(" ", "-").replace("/", "-")
    out_dir = OUTPUT_DIR / sprint_slug
    members_dir = out_dir / "members"
    members_dir.mkdir(parents=True, exist_ok=True)

    # Write individual docs
    for aid in TEAM:
        name     = TEAM[aid]["name"]
        filename = name.lower().replace(" ", "_") + ".md"
        doc      = generate_doc(aid, all_stats[aid], rankings,
                                sprint_name, sprint_start, sprint_end)
        path = members_dir / filename
        path.write_text(doc, encoding="utf-8")
        print(f"   📄 {name} → {path}")

    # Write index
    index = generate_index(sprint_name, sprint_start, sprint_end, all_stats, rankings)
    index_path = out_dir / "index.md"
    index_path.write_text(index, encoding="utf-8")
    print(f"\n✅ Index → {index_path}")

    # Also write a latest symlink-equivalent (overwrite latest/)
    latest_dir = OUTPUT_DIR / "latest"
    if latest_dir.exists():
        import shutil
        shutil.rmtree(latest_dir)
    import shutil
    shutil.copytree(out_dir, latest_dir)
    print(f"✅ Latest copy → {latest_dir}")

    print(f"\n🎉 Done! Docs at: {out_dir}")


if __name__ == "__main__":
    main()
