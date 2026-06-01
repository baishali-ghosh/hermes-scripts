
import keyring, requests

token = keyring.get_password("hermes", "JIRA_API_TOKEN")
auth = ("baishali.ghosh@uipath.com", token)
headers = {"Accept": "application/json"}
base = "https://uipath.atlassian.net"

# Search by name for Charan
for q in ["charan", "karpuram"]:
    r = requests.get(f"{base}/rest/api/2/user/search", params={"query": q}, auth=auth, headers=headers, timeout=20)
    users = r.json()
    for u in users:
        print(f"{u['displayName']} | {u.get('emailAddress','')} | {u['accountId']}")
