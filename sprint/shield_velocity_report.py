#!/usr/bin/env python3
"""
Shield Team — Biweekly Productivity & Velocity Report
Tracks: per-assignee velocity, status breakdown, story points, aged tickets
Jira: project=ENGCE, board=2456, org=uipath.atlassian.net

Auto-sweep actions:
  - Aged & stalled tickets (stuck >= AGED_STUCK_THRESHOLD days): adds Baishali as
    watcher (CC) and posts a reprioritization nudge comment.
  - Tickets missing story points: posts a comment @mentioning the assignee.
  - Both comments end with "— Auto sweep by Claude".
  - Skips if last comment already contains "Auto sweep by Claude" (dedup).
"""

import requests
import json
import os
from datetime import datetime, timezone
from collections import defaultdict

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
JIRA_BASE    = "https://uipath.atlassian.net"
JIRA_USER    = "baishali.ghosh@uipath.com"
JIRA_TOKEN   = _get_jira_token()
BOARD_ID     = 2456
PROJECT_KEY  = "ENGCE"

BAISHALI_ID  = "61289a45fc550900711d5544"   # Baishali's Jira account ID (CC / watcher)

# Aged-ticket auto-sweep thresholds
AGED_STUCK_THRESHOLD = 5    # days stuck in the same status before we flag + sweep
DONE_ACTUAL_SP_WINDOW_DAYS = 24  # days since Done transition to back-fill actual SP

# Statuses considered "completed"
DONE_STATUSES   = {"Done", "Closed", "Resolved", "Merged"}
ACTIVE_STATUSES = {"In Progress", "PR Review"}
BLOCKED_STATUSES = {"Pending", "Open", "To Do"}

auth    = (JIRA_USER, JIRA_TOKEN)
headers = {"Accept": "application/json"}

# ── Helpers ───────────────────────────────────────────────────────────────────
def get(url, params=None):
    r = requests.get(url, auth=auth, headers=headers, params=params, timeout=30)
    r.raise_for_status()
    return r.json()

def parse_date(s):
    if not s:
        return None
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

def transitioned_to_done_within(changelog_histories, done_statuses, threshold_days):
    """Return (True, transition_dt) if the issue was moved to a done status within
    threshold_days. Looks at the most recent Done transition only."""
    now = datetime.now(timezone.utc)
    for h in sorted(changelog_histories, key=lambda x: x["created"], reverse=True):
        for item in h["items"]:
            if item["field"] == "status" and item["toString"] in done_statuses:
                dt = parse_date(h["created"])
                if dt and (now - dt).days <= threshold_days:
                    return True, dt
                return False, None   # most recent Done transition is too old
    return False, None

def extract_comment_text(body):
    """Extract plain text from an Atlassian Document Format comment body."""
    text = ""
    if isinstance(body, dict):
        for block in body.get("content", []):
            for inline in block.get("content", []):
                if inline.get("type") == "text":
                    text += inline.get("text", "")
    else:
        text = str(body)
    return text

def get_last_comment(issue_key):
    """Fetch the most recent comment on an issue.
    Returns (author, created_dt, text, already_swept).
    already_swept=True if the last comment contains 'Auto sweep by Claude'.
    """
    try:
        data = get(f"{JIRA_BASE}/rest/api/3/issue/{issue_key}/comment",
                   params={"maxResults": 1, "orderBy": "-created"})
        comments = data.get("comments", [])
        if comments:
            c = comments[-1]
            author  = c.get("author", {}).get("displayName", "?")
            created = parse_date(c["created"])
            text    = extract_comment_text(c.get("body", {}))[:200]
            swept   = "Auto sweep by Claude" in text
            return author, created, text, swept
    except Exception:
        pass
    return None, None, "(no comments)", False

def add_watcher(issue_key, account_id):
    """Add account_id as a watcher on the issue. Returns True on success."""
    try:
        url = f"{JIRA_BASE}/rest/api/3/issue/{issue_key}/watchers"
        r = requests.post(
            url, auth=auth,
            headers={**headers, "Content-Type": "application/json"},
            data=json.dumps(account_id),   # body must be a JSON string, not object
            timeout=15
        )
        return r.status_code in (200, 204)
    except Exception:
        return False

def post_comment_adf(issue_key, paragraphs):
    """Post a comment built from a list of ADF paragraph content arrays.
    Each element of `paragraphs` is a list of ADF inline nodes.
    Returns True on success.
    """
    content = [{"type": "paragraph", "content": nodes} for nodes in paragraphs]
    body = {
        "body": {
            "version": 1,
            "type": "doc",
            "content": content
        }
    }
    try:
        url = f"{JIRA_BASE}/rest/api/3/issue/{issue_key}/comment"
        r = requests.post(
            url, auth=auth,
            headers={**headers, "Content-Type": "application/json"},
            json=body, timeout=15
        )
        return r.status_code in (200, 201)
    except Exception:
        return False

def post_aged_comment(issue_key, status, in_status_days, last_touch_days):
    """Post a reprioritization nudge on a stalled ticket."""
    paragraphs = [
        [
            {"type": "text", "text":
             f"⏰ This ticket has been in \"{status}\" status for {in_status_days} day(s)"
             f" (last updated {last_touch_days} day(s) ago) and appears to have stalled."},
        ],
        [
            {"type": "text", "text":
             "Please check with your manager for reprioritization or provide a status update."},
        ],
        [
            {"type": "text", "text": "— Auto sweep by Claude"},
        ],
    ]
    return post_comment_adf(issue_key, paragraphs)

def post_missing_sp_comment(issue_key, assignee_id, assignee_name):
    """Post a story-points nudge @mentioning the assignee."""
    paragraphs = [
        [
            {
                "type": "mention",
                "attrs": {"id": assignee_id, "text": f"@{assignee_name}"}
            },
            {"type": "text", "text":
             " Please update the story points on this ticket to enable accurate"
             " velocity calculation for the sprint."},
        ],
        [
            {"type": "text", "text": "— Auto sweep by Claude"},
        ],
    ]
    return post_comment_adf(issue_key, paragraphs)

def set_actual_sp(issue_key, value):
    """Set customfield_12629 (Actual Story Points) on an issue. Returns True on success."""
    try:
        r = requests.put(
            f"{JIRA_BASE}/rest/api/3/issue/{issue_key}",
            auth=auth,
            headers={**headers, "Content-Type": "application/json"},
            json={"fields": {"customfield_12629": float(value)}},
            timeout=15
        )
        return r.status_code in (200, 204)
    except Exception:
        return False

def post_actual_sp_done_comment(issue_key, assignee_id, assignee_name, estimated_sp, actual_set_to):
    """Post a comment on a Done ticket where Actual Story Points were missing.
    actual_set_to is the value we wrote (=estimated_sp), or None if no estimate existed.
    """
    if actual_set_to is not None:
        delta = actual_set_to - estimated_sp   # always 0 when defaulting actual=estimated
        delta_str = f"+{delta:.1f}" if delta >= 0 else f"{delta:.1f}"
        body_text = (
            f"✅ This ticket was closed without Actual Story Points set. "
            f"Estimated SP: {estimated_sp:.1f}. "
            f"Actual SP has been defaulted to {actual_set_to:.1f} (delta from estimated: {delta_str}). "
            f"Please update if actual effort differed."
        )
    else:
        body_text = (
            "✅ This ticket was closed without Actual Story Points set, "
            "and no Estimated Story Points were found either. "
            "Please fill in the Actual Story Points field to reflect actual effort."
        )
    paragraphs = [
        [
            {"type": "mention", "attrs": {"id": assignee_id, "text": f"@{assignee_name}"}},
            {"type": "text", "text": f" {body_text}"},
        ],
        [
            {"type": "text", "text": "— Auto sweep by Claude"},
        ],
    ]
    return post_comment_adf(issue_key, paragraphs)

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
            "fields": "summary,status,assignee,story_points,customfield_10016,customfield_12629,created,updated,priority,issuetype,changelog",
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

aged_candidates  = []   # tickets not done, age > 7 days
missing_sp_tickets = [] # non-done tickets with no story points (ENGCE only)
done_no_actual_sp  = [] # ALL-project tickets: Done in last 24d, actual SP not set

now = datetime.now(timezone.utc)

for issue in all_issues:
    f = issue["fields"]
    key           = issue["key"]

    # ── Done-ticket actual-SP sweep (ALL projects in sprint) ──────────────────
    actual_sp_raw = f.get("customfield_12629")
    if actual_sp_raw is None and f["status"]["name"] in DONE_STATUSES:
        histories = issue.get("changelog", {}).get("histories", [])
        moved, _  = transitioned_to_done_within(histories, DONE_STATUSES, DONE_ACTUAL_SP_WINDOW_DAYS)
        if moved:
            a_obj = f.get("assignee") or {}
            done_no_actual_sp.append({
                "key":          key,
                "assignee":     a_obj.get("displayName", "Unassigned"),
                "assignee_id":  a_obj.get("accountId", ""),
                "estimated_sp": f.get("customfield_10016"),   # may be None
                "status":       f["status"]["name"],
                "summary":      f.get("summary", "")[:80],
            })
    # ──────────────────────────────────────────────────────────────────────────

    # Skip tickets not in the ENGCE project — sprint may include SW, MST, etc.
    if not key.startswith(f"{PROJECT_KEY}-"):
        continue

    assignee_obj  = f.get("assignee") or {}
    assignee      = assignee_obj.get("displayName", "Unassigned")
    assignee_id   = assignee_obj.get("accountId", "")
    status        = f["status"]["name"]
    summary       = f.get("summary", "")[:80]
    sp_raw        = f.get("customfield_10016")         # None = field not set in Jira
    points        = sp_raw or 0                        # coerced for arithmetic
    created       = parse_date(f.get("created"))
    updated       = parse_date(f.get("updated"))
    age_days      = days_ago(created)
    last_touch    = days_ago(updated)

    # Changelog for time-in-status
    histories      = issue.get("changelog", {}).get("histories", [])
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

    # Track aged tickets: not done, created > 7 days ago
    if status not in DONE_STATUSES and age_days and age_days > 7:
        aged_candidates.append({
            "key": key,
            "assignee": assignee,
            "assignee_id": assignee_id,
            "status": status,
            "summary": summary,
            "age_days": age_days,
            "last_touch_days": last_touch,
            "in_status_days": in_status_days or 0,
            "points": points
        })

    # Track missing story points: not done, SP field genuinely unset (None), has an assignee
    if status not in DONE_STATUSES and sp_raw is None and assignee != "Unassigned" and assignee_id:
        missing_sp_tickets.append({
            "key": key,
            "assignee": assignee,
            "assignee_id": assignee_id,
            "status": status,
            "summary": summary,
        })

# Sort aged by how long in current status (most stuck first)
aged_candidates.sort(key=lambda x: x["in_status_days"], reverse=True)
top_aged = aged_candidates[:8]

# ── Fetch Last Comment for Top Aged Tickets ────────────────────────────────────
print(f"Fetching comments for {len(top_aged)} aged tickets...")
for t in top_aged:
    author, when, text, swept = get_last_comment(t["key"])
    t["last_comment_author"] = author
    t["last_comment_days"]   = days_ago(when) if when else None
    t["last_comment_text"]   = text or "(no comments)"
    t["already_swept"]       = swept

# ── Auto-Sweep: Aged / Stalled Tickets ────────────────────────────────────────
print("Running auto-sweep on aged/stalled tickets...")
sweep_aged_actions   = []   # list of dicts describing what was done
sweep_sp_actions     = []

for t in top_aged:
    if t["in_status_days"] < AGED_STUCK_THRESHOLD:
        continue                       # not stuck enough yet
    if t["already_swept"]:
        sweep_aged_actions.append({
            "key": t["key"], "assignee": t["assignee"],
            "in_status_days": t["in_status_days"],
            "action": "SKIPPED (already swept)"
        })
        continue

    actions_done = []
    # 1. Add Baishali as watcher (CC)
    ok_watch = add_watcher(t["key"], BAISHALI_ID)
    actions_done.append(f"watcher={'✅' if ok_watch else '❌'}")

    # 2. Post aged comment
    ok_comment = post_aged_comment(
        t["key"], t["status"], t["in_status_days"], t["last_touch_days"] or 0
    )
    actions_done.append(f"comment={'✅' if ok_comment else '❌'}")

    sweep_aged_actions.append({
        "key": t["key"], "assignee": t["assignee"],
        "in_status_days": t["in_status_days"],
        "action": ", ".join(actions_done)
    })

# ── Auto-Sweep: Missing Story Points ──────────────────────────────────────────
# Always re-post if SP is still missing — this is an intentional weekly nudge.
# We check the actual story points field value (not comment history) to decide.
print(f"Checking {len(missing_sp_tickets)} tickets for missing story points...")
for t in missing_sp_tickets:
    # sp_raw is None means SP is genuinely still unset — always remind
    ok = post_missing_sp_comment(t["key"], t["assignee_id"], t["assignee"])
    sweep_sp_actions.append({
        "key": t["key"], "assignee": t["assignee"],
        "action": f"comment={'✅' if ok else '❌'}"
    })

# ── Auto-Sweep: Done Tickets Missing Actual Story Points (ALL projects) ────────
print(f"Checking {len(done_no_actual_sp)} done tickets for missing actual story points...")
sweep_done_actual_sp_actions = []
for t in done_no_actual_sp:
    if not t["assignee_id"]:
        continue
    # Dedup: skip if already swept
    _, _, _, already_swept = get_last_comment(t["key"])
    if already_swept:
        sweep_done_actual_sp_actions.append({
            "key": t["key"], "assignee": t["assignee"],
            "action": "SKIPPED (already swept)"
        })
        continue

    estimated = t["estimated_sp"]
    if estimated is not None:
        ok_set = set_actual_sp(t["key"], estimated)
        actual_set_to = estimated if ok_set else None
    else:
        ok_set = False
        actual_set_to = None

    ok_comment = post_actual_sp_done_comment(
        t["key"], t["assignee_id"], t["assignee"], estimated, actual_set_to
    )
    sweep_done_actual_sp_actions.append({
        "key":           t["key"],
        "assignee":      t["assignee"],
        "estimated_sp":  estimated,
        "actual_set_to": actual_set_to,
        "action":        f"sp_set={'✅' if ok_set else '❌ (no estimate)'}, comment={'✅' if ok_comment else '❌'}"
    })

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
    pts_done  = int(s["points_done"])
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
    swept_flag  = "  🤖 [swept]" if not t["already_swept"] and t["in_status_days"] >= AGED_STUCK_THRESHOLD else ""
    W(f"""
  🕐 {t['key']}  [{t['status']}]{swept_flag}  — Age: {t['age_days']}d | In status: {t['in_status_days']}d | Last touched: {t['last_touch_days']}d ago
     Assignee : {t['assignee']}
     Summary  : {t['summary']}
     Points   : {int(t['points']) if t['points'] else '?'}
     Last comment ({comment_age}) by {t['last_comment_author'] or '—'}:
       \"{t['last_comment_text']}\"
""")

W("═" * 66)
W("  AUTO-SWEEP ACTIONS")
W("═" * 66)

W(f"\n  🕐 Aged/Stalled Tickets  (threshold: {AGED_STUCK_THRESHOLD}+ days in same status)")
if sweep_aged_actions:
    for a in sweep_aged_actions:
        W(f"    {a['key']}  [{a['in_status_days']}d stuck]  {a['assignee']}  →  {a['action']}")
else:
    W("    None — no tickets crossed the stuck threshold.")

W(f"\n  📊 Missing Story Points")
if sweep_sp_actions:
    for a in sweep_sp_actions:
        W(f"    {a['key']}  {a['assignee']}  →  {a['action']}")
else:
    W("    None — all active tickets have story points set.")

W(f"\n  ✅ Done Tickets — Actual SP Back-filled  (window: last {DONE_ACTUAL_SP_WINDOW_DAYS}d, all projects)")
if sweep_done_actual_sp_actions:
    for a in sweep_done_actual_sp_actions:
        est  = f"{a['estimated_sp']:.1f}" if a.get("estimated_sp") is not None else "—"
        act  = f"{a['actual_set_to']:.1f}" if a.get("actual_set_to") is not None else "—"
        W(f"    {a['key']}  {a['assignee']}  estimated={est}  actual_set={act}  →  {a['action']}")
else:
    W("    None — all recently-done tickets have Actual Story Points set.")

W("")
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
