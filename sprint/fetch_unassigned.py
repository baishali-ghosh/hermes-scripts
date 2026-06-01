import requests, os
from datetime import datetime, timezone

auth    = ("baishali.ghosh@uipath.com", os.environ["JIRA_API_TOKEN"])
headers = {"Accept": "application/json"}
BASE    = "https://uipath.atlassian.net"
KEYS    = ["ENGCE-57947","ENGCE-58328","ENGCE-56102","ENGCE-56103","ENGCE-57222","ENGCE-57778"]

def days_ago(s):
    if not s: return "?"
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            dt = datetime.strptime(s[:26] + s[26:].replace(":", ""), fmt)
            return str((datetime.now(timezone.utc) - dt).days) + "d ago"
        except: pass
    return "?"

for key in KEYS:
    r = requests.get(f"{BASE}/rest/api/3/issue/{key}",
        auth=auth, headers=headers,
        params={"fields": "summary,status,issuetype,created,updated,priority,comment"})
    resp = r.json()
    if "fields" not in resp:
        print(f"{key}: ERROR - {resp.get('errorMessages', resp)}\n")
        continue
    f = resp["fields"]
    status   = f["status"]["name"]
    itype    = (f.get("issuetype") or {}).get("name", "?")
    priority = (f.get("priority") or {}).get("name", "?")
    created  = days_ago(f.get("created"))
    updated  = days_ago(f.get("updated"))
    summary  = f.get("summary", "")

    comments = f.get("comment", {}).get("comments", [])
    if comments:
        c       = comments[-1]
        cauthor = c.get("author", {}).get("displayName", "?")
        cwhen   = days_ago(c.get("created"))
        body    = c.get("body", {})
        ctext   = ""
        if isinstance(body, dict):
            for block in body.get("content", []):
                for inline in block.get("content", []):
                    if inline.get("type") == "text":
                        ctext += inline.get("text", "")
        ctext = ctext[:150]
    else:
        cauthor, cwhen, ctext = "—", "—", "(no comments)"

    print(f"{key}  [{status}]  {itype}  |  Priority: {priority}")
    print(f"  Summary : {summary}")
    print(f"  Created : {created}  |  Updated: {updated}")
    print(f"  Comment : ({cwhen} by {cauthor}): {ctext}")
    print()
