import requests

TOKEN = "ATAT...FA0A"
auth    = ("baishali.ghosh@uipath.com", TOKEN)
headers = {"Accept": "application/json", "Content-Type": "application/json"}
BASE    = "https://uipath.atlassian.net"

# 1. Move both issues to backlog (removes sprint assignment)
r = requests.post(
    f"{BASE}/rest/agile/1.0/backlog/issue",
    auth=auth, headers=headers,
    json={"issues": ["ENGCE-56102", "ENGCE-57222"]}
)
print(f"Remove from sprint: {r.status_code} {r.text if r.text else 'OK'}")

# 2. Link ENGCE-56102 to JDBC epic ENGCE-48742
r2 = requests.put(
    f"{BASE}/rest/api/3/issue/ENGCE-56102",
    auth=auth, headers=headers,
    json={"fields": {"customfield_10014": "ENGCE-48742"}}
)
print(f"Link epic (customfield_10014): {r2.status_code} {r2.text[:300] if r2.text else 'OK'}")

if r2.status_code != 204:
    r3 = requests.put(
        f"{BASE}/rest/api/3/issue/ENGCE-56102",
        auth=auth, headers=headers,
        json={"update": {"customfield_10014": [{"set": "ENGCE-48742"}]}}
    )
    print(f"Link epic (update format): {r3.status_code} {r3.text[:300] if r3.text else 'OK'}")
