#!/usr/bin/env python3
"""Role Radar feed: checks company job boards for senior marketing/growth roles.

Runs with no AI and no extra packages (Python 3.9+ standard library only).
Each run:
  1. Reads companies.json.
  2. Pulls every open job from each company's job system (its public feed).
  3. Keeps senior marketing / growth / brand / community / fundraising titles.
  4. Compares with data/seen.json to find roles that are NEW since the last run
     and roles that have DISAPPEARED (closed).
  5. Writes data/report.md (short, for Molly and the Claude scan),
     data/open_roles.json (every matching open role) and updates data/seen.json.
"""
import json, re, sys, time, urllib.request, urllib.error
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
UA = "Mozilla/5.0 (RoleRadarFeed; personal job search)"
TIMEOUT = 25
STALE_DAYS = 60

# --- Title filter -----------------------------------------------------------
SENIOR = re.compile(r"\b(head|director|vp|vice[- ]president|chief|cmo|cgo|lead|leader|fractional|interim)\b", re.I)
FUNCTION = re.compile(
    r"\b(marketing|growth|brand|community|crm|lifecycle|retention|digital|audience|"
    r"communications?|comms|marcom|fundrais\w*|development|membership|supporter|"
    r"engagement|b2c|consumer|demand|acquisition|content|social|partnerships?)\b", re.I)
EXCLUDE = re.compile(
    r"\b(intern|internship|working student|werkstudent|trainee|assistant|coordinator|"
    r"specialist|associate|analyst|engineer|engineering|developer|designer|scientist|"
    r"product manager|account (manager|executive)|sales (manager|representative)|"
    r"recruit\w*|people|legal|finance|accountant|software|data engineer|"
    r"business development representative|sdr|bdr)\b", re.I)
# "Lead" alone is weak: only keep it with a marketing/growth word right next to it.
LEAD_ONLY = re.compile(r"^(?!.*\b(head|director|vp|vice[- ]president|chief|cmo)\b).*\blead\b", re.I)
STRONG_FN = re.compile(r"\b(marketing|growth|brand|community|crm|lifecycle|fundrais\w*)\b", re.I)


def is_target(title: str) -> bool:
    t = title or ""
    if EXCLUDE.search(t) and not re.search(r"\b(head|director|vp|chief)\b", t, re.I):
        return False
    if not (SENIOR.search(t) and FUNCTION.search(t)):
        return False
    if LEAD_ONLY.search(t) and not STRONG_FN.search(t):
        return False
    if re.search(r"\b(senior )?manager\b", t, re.I) and not re.search(r"\b(head|director|vp|chief|lead)\b", t, re.I):
        return False
    return True


# --- HTTP ---------------------------------------------------------------------
def get(url, data=None, accept="application/json"):
    headers = {"User-Agent": UA, "Accept": accept}
    body = None
    if data is not None:
        body = json.dumps(data).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, headers=headers)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return r.read()


def jget(url, data=None):
    return json.loads(get(url, data).decode("utf-8", "replace"))


def iso(v):
    """Normalise dates (ISO strings or epoch ms) to YYYY-MM-DD, or ''."""
    if v in (None, ""):
        return ""
    try:
        if isinstance(v, (int, float)):
            return datetime.fromtimestamp(v / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
        return str(v)[:10]
    except Exception:
        return ""


# --- One function per job system ---------------------------------------------
def f_greenhouse(slug, eu=False):
    host = "boards-api.eu.greenhouse.io" if eu else "boards-api.greenhouse.io"
    d = jget(f"https://{host}/v1/boards/{slug}/jobs")
    for j in d.get("jobs", []):
        yield {"id": str(j["id"]), "title": j.get("title", ""),
               "location": (j.get("location") or {}).get("name", ""),
               "posted": iso(j.get("first_published") or j.get("updated_at")),
               "deadline": iso(j.get("application_deadline")),
               "url": j.get("absolute_url", "")}


def f_lever(slug):
    for j in jget(f"https://api.lever.co/v0/postings/{slug}?mode=json"):
        cat = j.get("categories") or {}
        yield {"id": j["id"], "title": j.get("text", ""),
               "location": " / ".join(x for x in [cat.get("location", ""), j.get("workplaceType", "")] if x),
               "posted": iso(j.get("createdAt")), "deadline": "",
               "url": j.get("hostedUrl", "")}


def f_recruitee(host):
    d = jget(f"https://{host}/api/offers/")
    for j in d.get("offers", []):
        loc = j.get("location") or ", ".join(x for x in [j.get("city"), j.get("country")] if x)
        if j.get("remote"):
            loc = (loc + " / remote").strip(" /")
        yield {"id": str(j["id"]), "title": j.get("title", ""), "location": loc or "",
               "posted": iso(j.get("published_at") or j.get("created_at")), "deadline": iso(j.get("close_at")),
               "url": j.get("careers_url") or f"https://{host}/o/{j.get('slug','')}"}


def f_workable(slug):
    try:
        d = jget(f"https://apply.workable.com/api/v3/accounts/{slug}/jobs",
                 {"query": "", "location": [], "department": [], "worktype": [], "remote": []})
        for j in d.get("results", []):
            loc = j.get("location") or {}
            where = ", ".join(x for x in [loc.get("city"), loc.get("country")] if x)
            if j.get("remote"):
                where = (where + " / remote").strip(" /")
            yield {"id": j.get("shortcode") or str(j.get("id")), "title": j.get("title", ""),
                   "location": where, "posted": iso(j.get("published")), "deadline": "",
                   "url": f"https://apply.workable.com/{slug}/j/{j.get('shortcode')}/"}
    except urllib.error.HTTPError:
        d = jget(f"https://apply.workable.com/api/v1/widget/accounts/{slug}")
        for j in d.get("jobs", []):
            where = ", ".join(x for x in [j.get("city"), j.get("country")] if x)
            if j.get("telecommuting"):
                where = (where + " / remote").strip(" /")
            yield {"id": j.get("shortcode", ""), "title": j.get("title", ""), "location": where,
                   "posted": iso(j.get("published_on") or j.get("created_at")), "deadline": "",
                   "url": j.get("url") or j.get("application_url", "")}


def f_ashby(slug):
    d = jget(f"https://api.ashbyhq.com/posting-api/job-board/{slug}")
    for j in d.get("jobs", []):
        if j.get("isListed") is False:
            continue
        loc = j.get("location", "")
        if j.get("isRemote"):
            loc = (loc + " / remote").strip(" /")
        yield {"id": j["id"], "title": j.get("title", ""), "location": loc,
               "posted": iso(j.get("publishedAt")), "deadline": "", "url": j.get("jobUrl", "")}


def f_personio(slug):
    root = ET.fromstring(get(f"https://{slug}.jobs.personio.com/xml", accept="application/xml"))
    for p in root.iter("position"):
        pid = (p.findtext("id") or "").strip()
        yield {"id": pid, "title": (p.findtext("name") or "").strip(),
               "location": (p.findtext("office") or "").strip(),
               "posted": iso((p.findtext("createdAt") or "").strip()), "deadline": "",
               "url": f"https://{slug}.jobs.personio.com/job/{pid}?display=en"}


def f_smartrecruiters(slug):
    d = jget(f"https://api.smartrecruiters.com/v1/companies/{slug}/postings?limit=100")
    for j in d.get("content", []):
        loc = j.get("location") or {}
        where = ", ".join(x for x in [loc.get("city"), loc.get("country")] if x)
        if loc.get("remote"):
            where = (where + " / remote").strip(" /")
        yield {"id": str(j["id"]), "title": j.get("name", ""), "location": where,
               "posted": iso(j.get("releasedDate")), "deadline": "",
               "url": f"https://jobs.smartrecruiters.com/{slug}/{j['id']}"}


FETCHERS = {
    "greenhouse": lambda s: f_greenhouse(s),
    "greenhouse_eu": lambda s: f_greenhouse(s, eu=True),
    "lever": f_lever, "recruitee": f_recruitee, "workable": f_workable,
    "ashby": f_ashby, "personio": f_personio, "smartrecruiters": f_smartrecruiters,
}


def days_ago(d, today):
    try:
        return (today - datetime.strptime(d, "%Y-%m-%d").date()).days
    except Exception:
        return None


def main(fetchers=FETCHERS):
    cfg = json.loads((ROOT / "companies.json").read_text())
    DATA.mkdir(exist_ok=True)
    seen_path = DATA / "seen.json"
    seen = json.loads(seen_path.read_text()) if seen_path.exists() else {}
    first_run = not seen
    now = datetime.now(timezone.utc)
    today = now.date()
    today_s = today.isoformat()

    open_roles, errors, checked = {}, [], 0
    for c in cfg["companies"]:
        fn = fetchers.get(c["ats"])
        if not fn:
            errors.append(f"{c['name']}: unknown job system '{c['ats']}'")
            continue
        try:
            jobs = list(fn(c["slug"]))
            checked += 1
        except Exception as e:  # keep going; report it
            errors.append(f"{c['name']} ({c['ats']}:{c['slug']}): {type(e).__name__} {str(e)[:80]}")
            continue
        for j in jobs:
            if not is_target(j["title"]):
                continue
            key = f"{c['ats']}:{c['slug']}:{j['id']}"
            prev = seen.get(key, {})
            open_roles[key] = {
                "company": c["name"], "lane": c.get("lane", ""), "love": bool(c.get("love")),
                "title": j["title"], "location": j["location"], "url": j["url"],
                "posted": j["posted"], "deadline": j["deadline"],
                "first_seen": prev.get("first_seen", today_s), "last_seen": today_s,
            }
        time.sleep(0.3)

    failed = {e.split(" (")[0].split(":")[0] for e in errors}
    new = [r for k, r in open_roles.items() if k not in seen]
    closed = [r for k, r in seen.items()
              if k not in open_roles and r.get("company") not in failed and not r.get("closed")]

    # Keep closed roles in seen.json (marked) so a re-listed role isn't "new" again.
    for k, r in seen.items():
        if k not in open_roles and r.get("company") not in failed:
            r["closed"] = r.get("closed") or today_s
    seen.update({k: dict(v, closed="") for k, v in open_roles.items()})
    seen_path.write_text(json.dumps(seen, indent=1, sort_keys=True))

    def age(r):
        d = days_ago(r["posted"], today)
        return "date unknown" if d is None else ("today" if d == 0 else f"{d}d ago")

    def fresh(r):
        d = days_ago(r["posted"], today)
        return r["love"] or (d is not None and d <= STALE_DAYS)

    new_fresh = [r for r in new if fresh(r)]
    new_old = [r for r in new if not fresh(r)]
    rows = sorted(open_roles.values(), key=lambda r: r["posted"] or "0", reverse=True)
    (DATA / "open_roles.json").write_text(json.dumps(rows, indent=1))

    L = [f"# Role Radar feed — {today_s}", "",
         f"Checked {checked} of {len(cfg['companies'])} company job boards. "
         f"{len(rows)} matching roles open. {len(new_fresh)} new and fresh, {len(closed)} closed since last run.", ""]
    if first_run:
        L += ["_First run: everything below is the starting list, not necessarily new today._", ""]
    def line(r):
        dl = f" · closes {r['deadline']}" if r["deadline"] else ""
        heart = " ♥" if r["love"] else ""
        return f"- **{r['company']}{heart}** — {r['title']} · {r['location'] or 'location n/a'} · posted {r['posted'] or '?'} ({age(r)}){dl} · {r['url']}"
    L += ["## New since last run (posted ≤60 days, or a loved brand)", ""] + ([line(r) for r in new_fresh] or ["- none"]) + [""]
    if new_old:
        L += ["## Newly seen but posted >60 days ago (ignore unless loved)", ""] + [line(r) for r in new_old] + [""]
    L += ["## Closed since last run (gone from the company's own board)", ""]
    L += [f"- {r['company']} — {r['title']} · {r.get('url','')}" for r in closed] or ["- none"]
    L += ["", "## All matching open roles", ""] + ([line(r) for r in rows] or ["- none"])
    if errors:
        L += ["", "## Boards that could not be read (fix the slug in companies.json)", ""] + [f"- {e}" for e in errors]
    (DATA / "report.md").write_text("\n".join(L) + "\n")
    print("\n".join(L[:4]))
    print(f"new_fresh={len(new_fresh)} closed={len(closed)} errors={len(errors)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
