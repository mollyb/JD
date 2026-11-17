# Role Radar feed

A free daily check of Molly's watchlist companies' own job boards. No AI, no tokens.
Every morning it lists senior marketing, growth, brand, community and fundraising roles,
with the **real posting date** and a **direct link**, and shows what is **new** and what has **closed**
since the day before.

Results: `data/report.md` (read this), `data/open_roles.json` (every matching open role).

## One-time setup (about 10 minutes)

1. Sign in to github.com (create a free account if you don't have one).
2. Click **+ → New repository**. Name it `role-radar-feed`. Choose **Public** (so the Claude scan can read the report; it only contains public job listings) and click **Create repository**.
3. On the new repo page click **uploading an existing file**, drag in everything from this folder (`radar.py`, `companies.json`, `README.md`, the `data` folder and the `.github` folder), then **Commit changes**.
   - If the `.github` folder doesn't upload by drag-and-drop, click **Add file → Create new file**, type `.github/workflows/radar.yml` as the name, and paste in the contents of `radar.yml`.
4. Go to **Settings → Actions → General → Workflow permissions**, choose **Read and write permissions**, and **Save**.
5. Go to the **Actions** tab, click **Role Radar feed → Run workflow**. After about a minute, open `data/report.md`.

From then on it runs by itself every day at about 4–5am Pacific.

The first run lists every matching open role as a starting point. From the second day, "New since last run" really means new.

## Adding or fixing a company

Edit `companies.json` on GitHub (pencil icon) and copy a line. Each company needs its job system and ID:

| Job system | Where to find the ID | Example |
|---|---|---|
| greenhouse | `job-boards.greenhouse.io/<id>` | `wikimedia` |
| greenhouse_eu | `job-boards.eu.greenhouse.io/<id>` | `thesocialhub` |
| lever | `jobs.lever.co/<id>` | `bloomon` |
| recruitee | the careers site's address | `livezoku.recruitee.com` |
| workable | `apply.workable.com/<id>` | `tiqets` |
| ashby | `jobs.ashbyhq.com/<id>` | `toogoodtogo` |
| personio | `<id>.jobs.personio.com` | `fairphone` |
| smartrecruiters | `jobs.smartrecruiters.com/<id>` | `subjecttoclimate` |

Set `"love": true` for brands she loves (their roles show even when old or undated).
Boards that fail are listed at the bottom of the report so a wrong ID is easy to spot.

## What it doesn't do

It doesn't judge fit, search the wider web, or update the Role Radar tracker. The Claude scan (Mon and Thu)
reads this report, scores the new roles and adds the good ones to the tracker.
