
import keyring, requests, json

token = keyring.get_password("hermes", "JIRA_API_TOKEN")
auth = ("baishali.ghosh@uipath.com", token)
headers = {"Accept": "application/json"}
base = "https://uipath.atlassian.net"

emails = [
    "rahul.katikineni@uipath.com",
    "charan.karpuram@uipath.com",
    "ojal.kumar@uipath.com",
    "rohit.sharma@uipath.com",
    "sanjeet.manna@uipath.com",
    "pritish.saraf@uipath.com",
    "shyam.gupta@uipath.com",
]

for email in emails:
    r = requests.get(f"{base}/rest/api/2/user/search", params={"query": email}, auth=auth, headers=headers, timeout=20)
    users = r.json()
    if users:
        u = users[0]
        print(f"{u['displayName']} | {u.get('emailAddress','')} | {u['accountId']}")
    else:
        print(f"NOT FOUND: {email}")
