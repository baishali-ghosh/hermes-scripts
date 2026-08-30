# I automated my sprint planning with AI. Here's the setup.

*Series: How I use AI agents to run my own engineering team — Part 1 of 4*

---

Every Monday used to look the same.

Open Jira. Check what's blocking. Open Slack. Scroll through 20 channels to see what landed over the weekend. Open Confluence. Figure out who's doing what this sprint. Open my calendar. Prep for 1:1s.

By the time I'd assembled enough context to actually *lead* the sprint, half the morning was gone.

I'm a tech lead on a platform team. We ship integrations, connectors, and agentic orchestration infrastructure. The irony wasn't lost on me — I was manually doing work that AI agents are literally designed to do.

So I stopped doing it manually.

---

## The problem wasn't effort. It was context switching.

The information I needed every Monday existed. It was just spread across four tools, 23 Slack channels, two GitHub orgs, and a Jira board with 200+ tickets.

No single tool gave me a unified picture. And assembling that picture myself — every single week — was costing me 2–3 hours of deep focus time I didn't have.

What I actually needed wasn't a better dashboard. I needed an agent that could do the assembly for me, surface what mattered, and let me walk into my week already oriented.

---

## The architecture (it's simpler than it sounds)

I use a local AI orchestration layer with a set of cron jobs wired to my actual work tools.

Here's what runs automatically, before I've had my morning chai:

**Slack ask monitor** — scans 23 channels, categorizes incoming asks by team (DAP, Connectors, Case Management, X-team), surfaces anything that needs my attention. Runs daily.

**Sprint planning reminder** — two weeks before planning, auto-pulls the next 3 sprints, flags unplanned tickets, and posts a structured briefing to my team Slack. I show up to planning already knowing the shape of it.

**PR aging monitor** — tracks open PRs across my team (8 engineers, 3 repos), flags anything stale beyond 48 hours, auto-tags the author. No more PRs dying silently.

**Catch-up digest** — Monday morning, I get a single Telegram message: Slack mentions, DMs, key Jira updates, new PRs. 10 hours of overnight activity, summarized in 2 minutes.

Everything posts to the right place automatically. I don't check it — it comes to me.

---

## What Monday looks like now

I wake up. I read my digest. I know:
- What's blocked
- What's waiting on me
- What my team shipped over the weekend
- What's at risk this sprint

I walk into standups oriented. I walk into 1:1s prepared. I stopped being the bottleneck on context that I was assembling anyway.

That's it. That's the unlock.

---

## What's next

Next week I'll share the **actual scripts** — the exact code running these automations, what APIs they call, and how you can adapt them for your own team.

It's not magic. It's about 400 lines of Python and a clear-headed decision about what information actually matters.

*→ Subscribe so you don't miss Part 2.*

---

*Baishali Ghosh is a tech lead building agentic orchestration infrastructure. She writes about engineering, AI agents, and navigating tech as a woman who builds.*
