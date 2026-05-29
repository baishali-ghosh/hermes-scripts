#!/usr/bin/env python3
"""
Shield Team — Biweekly Productivity & Velocity Report
Tracks: per-assignee velocity, status breakdown, story points, aged tickets
Jira: project=ENGCE, board=2456, org=uipath.atlassian.net
"""

import requests
import json
import os
from datetime import datetime, timezone
from collections import defaultdict

# ── Config ────────────────────────────────────────────────────────────────────
JIRA_BASE    = "https://uipath.atlassian.net"
JIRA_USER    = "baishali.ghosh@uipath.com"
JIRA_TOKEN   = os.environ.get("JIRA_API_TOKEN", "")
BOARD_ID     = 2456
PROJECT_KEY  = "ENGCE"

# Statuses considered "completed"
DONE_STATUSES   = {"Done", "Closed", "Resolved", "Merged"}
ACTIVE_STATUSES = {"In Progress", "PR Review"}
BLOCKED_STATUSES = {"Pending", "Open", "To Do"}

auth = (JIRA_USER, JIRA_TOKEN)
headers = {"Accept": "application/json"}

# ── Helpers ───────────────────────────────────────────────────────────────────
def get(url, params=None):
    r = requests.get(url, auth=auth, headers=headers, params=params, timeout=30)
    r.raise_for_status()
    return r.json()

def parse_date(s):
    if not s:
        return None
    # Handle both with and without microseconds
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            return datetime.strptime(s[:26] + s[26:].replace(":", ""), fmt)
        except ValueError:
            continue
    return None

def days_ago(dt):
    if not dt:
        return None
    now = datetime.now(timezone.utc)
    return (now - dt).days

def days_in_status(changelog_histories, current_status):
    """Find how many days the issue has been in its current status."""
    last_transition = None
    for h in sorted(changelog_histories, key=lambda x: x["created"], reverse=True):
        for item in h["items"]:
            if item["field"] == "status" and item["toString"] == current_status:
                last_transition = parse_date(h["created"])
                break
        if last_transition:
            break
    return days_ago(last_transition)

def get_last_comment(issue_key):
    """Fetch the most recent comment on an issue."""
    try:
        data = get(f"{JIRA_BASE}/rest/api/3/issue/{issue_key}/comment",
                   params={"maxResults": 1, "orderBy": "-created"})
        comments = data.get("comments", [])
        if comments:
            c = comments[-1]
            author = c.get("author", {}).get("displayName", "?")
            created = parse_date(c["created"])
            # Extract plain text from body (Atlassian Document Format)
            body = c.get("body", {})
            text = ""
            if isinstance(body, dict):
                for block in body.get("content", []):
                    for inline in block.get("content", []):
                        if inline.get("type") == "text":
                            text += inline.get("text", "")
            else:
                text = str(body)
            return author, created, text[:200]
    except Exception:
        pass
    return None, None, None

# ── Fetch Active Sprint ────────────────────────────────────────────────────────
print("Fetching active sprint...")
sprint_data = get(f"{JIRA_BASE}/rest/agile/1.0/board/{BOARD_ID}/sprint",
                  params={"state": "active"})
sprints = sprint_data.get("values", [])
# Find the Shield sprint
shield_sprint = next(
    (s for s in sprints if "Shield" in s.get("name", "")),
    sprints[0] if sprints else None
)
if not shield_sprint:
    print("ERROR: No active sprint found.")
    exit(1)

sprint_id   = shield_sprint["id"]
sprint_name = shield_sprint["name"]
sprint_end  = parse_date(shield_sprint.get("endDate"))
days_left   = days_ago(sprint_end)
days_left_str = f"{abs(days_left)} days left" if days_left and days_left < 0 else (f"ended {days_left} days ago" if days_left else "?")

print(f"Sprint: {sprint_name} (ID {sprint_id}) — {days_left_str}")

# ── Fetch All Issues ───────────────────────────────────────────────────────────
print("Fetching sprint issues...")
all_issues = []
start = 0
while True:
    batch = get(
        f"{JIRA_BASE}/rest/agile/1.0/sprint/{sprint_id}/issue",
        params={
            "startAt": start,
            "maxResults": 50,
            "fields": "summary,status,assignee,story_points,customfield_10016,created,updated,priority,issuetype,changelog",
            "expand": "changelog"
        }
    )
    all_issues.extend(batch["issues"])
    if start + 50 >= batch["total"]:
        break
    start += 50

print(f"Total issues fetched: {len(all_issues)}")

# ── Per-Assignee Stats ─────────────────────────────────────────────────────────
stats = defaultdict(lambda: {
    "total": 0, "done": 0, "active": 0, "blocked": 0, "other": 0,
    "points_total": 0, "points_done": 0,
    "statuses": defaultdict(int),
    "issues": []
})

aged_candidates = []  # (age_days, key, assignee, status, summary, days_in_current_status)

now = datetime.now(timezone.utc)

for issue in all_issues:
    f = issue["fields"]
    key        = issue["key"]
    assignee   = (f.get("assignee") or {}).get("displayName", "Unassigned")
    status     = f["status"]["name"]
    summary    = f.get("summary", "")[:80]
    points     = f.get("customfield_10016") or 0  # story points
    created    = parse_date(f.get("created"))
    updated    = parse_date(f.get("updated"))
    age_days   = days_ago(created)
    last_touch = days_ago(updated)

    # Changelog for time-in-status
    histories  = issue.get("changelog", {}).get("histories", [])
    in_status_days = days_in_status(histories, status)

    s = stats[assignee]
    s["total"] += 1
    s["points_total"] += points
    s["statuses"][status] += 1
    s["issues"].append(key)

    if status in DONE_STATUSES:
        s["done"] += 1
        s["points_done"] += points
    elif status in ACTIVE_STATUSES:
        s["active"] += 1
    else:
        s["blocked"] += 1

    # Track aged tickets: not done, created > 7 days ago, or stuck in status > 5 days
    if status not in DONE_STATUSES and age_days and age_days > 7:
        aged_candidates.append({
            "key": key,
            "assignee": assignee,
            "status": status,
            "summary": summary,
            "age_days": age_days,
            "last_touch_days": last_touch,
            "in_status_days": in_status_days or 0,
            "points": points
        })

# Sort aged by how long in current status (most stuck first)
aged_candidates.sort(key=lambda x: x["in_status_days"], reverse=True)
top_aged = aged_candidates[:8]

# ── Fetch Last Comment for Top Aged Tickets ────────────────────────────────────
print(f"Fetching comments for {len(top_aged)} aged tickets...")
for t in top_aged:
    author, when, text = get_last_comment(t["key"])
    t["last_comment_author"] = author
    t["last_comment_days"] = days_ago(when) if when else None
    t["last_comment_text"] = text or "(no comments)"

# ── Report Generation ──────────────────────────────────────────────────────────
report_date = now.strftime("%Y-%m-%d %H:%M UTC")
lines = []
W = lines.append

W(f"╔══════════════════════════════════════════════════════════════╗")
W(f"  Shield Team — Biweekly Productivity & Velocity Report")
W(f"  Sprint: {sprint_name}  |  Generated: {report_date}")
W(f"  {days_left_str.upper()}  |  Total Issues: {len(all_issues)}")
W(f"╚══════════════════════════════════════════════════════════════╝")

W("")
W("═" * 66)
W("  PER-ASSIGNEE BREAKDOWN")
W("═" * 66)

# Sort by total issues desc
for name, s in sorted(stats.items(), key=lambda x: -x[1]["total"]):
    if name == "Unassigned":
        continue
    completion_rate = round(100 * s["done"] / s["total"]) if s["total"] else 0
    pts_done = int(s["points_done"])
    pts_total = int(s["points_total"])

    status_str = ", ".join(f"{k}:{v}" for k, v in sorted(s["statuses"].items()))

    W(f"\n  ▸ {name}")
    W(f"    Issues   : {s['total']} total | {s['done']} done | {s['active']} active | {s['blocked']} blocked/open")
    W(f"    Points   : {pts_done}/{pts_total} completed ({completion_rate}% done rate)")
    W(f"    Statuses : {status_str}")

# Unassigned
if "Unassigned" in stats:
    u = stats["Unassigned"]
    status_str = ", ".join(f"{k}:{v}" for k, v in sorted(u["statuses"].items()))
    W(f"\n  ⚠️  Unassigned")
    W(f"    Issues   : {u['total']} total | {status_str}")
    W(f"    Keys     : {', '.join(u['issues'])}")

W("")
W("═" * 66)
W("  TEAM VELOCITY SUMMARY")
W("═" * 66)

total_done   = sum(s["done"] for s in stats.values())
total_active = sum(s["active"] for s in stats.values())
total_open   = sum(s["blocked"] for s in stats.values())
total_pts_done  = int(sum(s["points_done"] for s in stats.values()))
total_pts_total = int(sum(s["points_total"] for s in stats.values()))

W(f"\n  Issues Done      : {total_done} / {len(all_issues)}")
W(f"  In Progress      : {total_active}")
W(f"  Blocked / Open   : {total_open}")
W(f"  Story Points Done: {total_pts_done} / {total_pts_total}")
W(f"  Sprint Completion: {round(100*total_done/len(all_issues))}%")

W("")
W("═" * 66)
W("  LONGEST AGED / STUCK TICKETS  (Top 8)")
W("═" * 66)

for t in top_aged:
    comment_age = f"{t['last_comment_days']}d ago" if t["last_comment_days"] is not None else "never"
    W(f"""
  🕐 {t['key']}  [{t['status']}]  — Age: {t['age_days']}d | In status: {t['in_status_days']}d | Last touched: {t['last_touch_days']}d ago
     Assignee : {t['assignee']}
     Summary  : {t['summary']}
     Points   : {int(t['points']) if t['points'] else '?'}
     Last comment ({comment_age}) by {t['last_comment_author'] or '—'}:
       \"{t['last_comment_text']}\"
""")

W("═" * 66)
W(f"  Report complete — {report_date}")
W("═" * 66)

report = "\n".join(lines)
print(report)

# Save to file
out_path = os.path.join(os.path.dirname(__file__), "shield_velocity_latest.txt")
with open(out_path, "w", encoding="utf-8") as f:
    f.write(report)
print(f"\nSaved to: {out_path}")
