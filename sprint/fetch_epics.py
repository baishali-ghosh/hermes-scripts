import requests, os
from datetime import datetime, timezone

JIRA_BASE  = "https://uipath.atlassian.net"
JIRA_USER  = "baishali.ghosh@uipath.com"
JIRA_TOKEN = os.environ.get("JIRA_API_TOKEN", "")
auth       = (JIRA_USER, JIRA_TOKEN)
headers    = {"Accept": "application/json"}

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
    return (datetime.now(timezone.utc) - dt).days

jql = "project = ENGCE AND issuetype = Epic AND statusCategory != Done ORDER BY updated DESC"
start = 0
epics = []
while True:
    data = get(f"{JIRA_BASE}/rest/api/3/search/approximate", {
        "jql": jql, "startAt": start, "maxResults": 50,
        "fields": "summary,status,assignee,created,updated,priority"
    })
    epics.extend(data["issues"])
    if start + 50 >= data["total"]:
        break
    start += 50

print(f"TOTAL:{len(epics)}")
for e in epics:
    f        = e["fields"]
    assignee = (f.get("assignee") or {}).get("displayName", "Unassigned")
    status   = f["status"]["name"]
    updated  = days_ago(parse_date(f.get("updated")))
    created  = days_ago(parse_date(f.get("created")))
    priority = (f.get("priority") or {}).get("name", "?")
    summary  = f.get("summary", "")
    print(f"{e['key']}|{status}|{assignee}|{updated}|{created}|{priority}|{summary}")
