import os
import asyncio
import aiohttp
import json
import re
import time
from datetime import datetime, timezone
from xml.etree import ElementTree
from bs4 import BeautifulSoup
import anthropic as _anthropic

DEEPSEEK_API_KEY = os.environ["DEEPSEEK_API_KEY"]
SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]
RUN_INTERVAL_HOURS = 24

SB = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}

deepseek = _anthropic.Anthropic(
    api_key=DEEPSEEK_API_KEY,
    base_url="https://api.deepseek.com/anthropic"
)

SKILLS = [
    "multi-agent system design", "autonomous pipeline architecture",
    "prompt engineering", "LLM integration", "Anthropic API", "DeepSeek",
    "agent memory systems", "Mem0", "Zep", "RAG", "vector search", "pgvector",
    "MCP server integration", "Model Context Protocol",
    "AI agent development", "agentic workflows", "AI automation",
    "Python", "Docker", "Docker Compose", "Dockerfile",
    "Railway", "Coolify", "Vercel", "Traefik",
    "GitHub Actions", "CI/CD", "webhooks",
    "server hardening", "Linux administration", "SSH",
    "cron scheduling", "REST API design",
    "Supabase", "PostgreSQL", "MariaDB",
    "data pipeline design", "lead scoring systems",
    "RLS", "schema design", "web scraping", "data extraction",
    "Next.js", "React", "TypeScript", "Vite",
    "dashboard design", "full-stack development",
    "performance marketing", "paid traffic", "media buying",
    "affiliate marketing", "cold email", "outreach automation",
    "conversion optimization", "SEO", "AEO", "content pipelines",
    "growth marketing", "B2B SaaS", "GTM strategy",
    "lead generation", "email deliverability",
    "Stripe", "billing integration", "Cloudflare", "DNS management",
    "WordPress", "Brevo", "email infrastructure",
    "B2B SaaS product building", "technical founder",
    "venture studio operations", "AI product management",
]

LOCATION_BLACKLIST = [
    "us only", "usa only", "united states only", "u.s. only", "u.s. residents only",
    "must be located in the us", "must reside in the us", "must be based in the us",
    "authorized to work in the us", "us citizens only", "us work authorization",
    "north america only", "canada only", "uk only", "australia only",
    "est required", "pst required", "cst required", "et only", "pt only",
    "eastern time required", "pacific time required",
    "must overlap with est", "must overlap with pst",
    "in-office", "on-site", "onsite required", "not remote",
    "no remote", "hybrid only", "local candidates only",
    "residing in the us", "residents of the us", "reside in the us",
    "based in the us", "located in the us", "within the us",
    "open to us", "us-based", "open to candidates in the us",
    "must be in the us", "only open to", "restricted to",
    "right to work in the uk", "right to work in the us",
    "eu residents only", "european union only",
]

def is_location_friendly(job):
    text = (job.get("title", "") + " " + job.get("raw_description", "")).lower()
    for phrase in LOCATION_BLACKLIST:
        if phrase in text:
            return False
    return True

async def fetch_remotive(session):
    jobs = []
    categories = ["software-dev", "devops-sysadmin", "marketing", "data"]
    for cat in categories:
        try:
            async with session.get(f"https://remotive.com/api/remote-jobs?category={cat}&limit=100") as r:
                data = await r.json()
                for j in data.get("jobs", []):
                    jobs.append({
                        "url": j.get("url", ""),
                        "title": j.get("title", ""),
                        "company": j.get("company_name", ""),
                        "source": "remotive",
                        "salary": j.get("salary", ""),
                        "posted_at": j.get("publication_date", ""),
                        "raw_description": j.get("description", "")[:3000]
                    })
        except Exception as e:
            print(f"Remotive error ({cat}): {e}")
    return jobs

async def fetch_remoteok(session):
    jobs = []
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        async with session.get("https://remoteok.com/api", headers=headers) as r:
            data = await r.json()
            for j in data:
                if not isinstance(j, dict) or "slug" not in j:
                    continue
                jobs.append({
                    "url": f"https://remoteok.com/remote-jobs/{j.get('slug','')}",
                    "title": j.get("position", ""),
                    "company": j.get("company", ""),
                    "source": "remoteok",
                    "salary": f"{j.get('salary_min','')} - {j.get('salary_max','')}".strip(" -"),
                    "posted_at": datetime.fromtimestamp(j.get("epoch", 0), tz=timezone.utc).isoformat() if j.get("epoch") else "",
                    "raw_description": j.get("description", "")[:3000]
                })
    except Exception as e:
        print(f"RemoteOK error: {e}")
    return jobs

async def fetch_himalayas(session):
    jobs = []
    keywords = ["AI agent", "LLM", "Python developer", "performance marketing", "growth marketing", "DevOps", "AI automation"]
    seen = set()
    for kw in keywords:
        try:
            async with session.get(f"https://himalayas.app/jobs/api/search?q={kw}&limit=50") as r:
                data = await r.json()
                for j in data.get("jobs", []):
                    url = j.get("applicationLink") or j.get("url", "")
                    if url in seen:
                        continue
                    # Filter by locationRestrictions and timezoneRestrictions
                    loc = j.get("locationRestrictions") or []
                    tz = j.get("timezoneRestrictions") or []
                    # Skip if restricted to specific countries
                    if loc:
                        skip = False
                        for l in loc:
                            l_lower = str(l).lower()
                            if any(x in l_lower for x in ["united states", "canada", "australia", "uk", "united kingdom"]):
                                skip = True
                                break
                        if skip:
                            continue
                    # Skip if timezone locked to Americas only (all offsets between -10 and -3)
                    if tz and all(-10 <= float(t) <= -3 for t in tz):
                        continue
                    seen.add(url)
                    company = j.get("companyName") or (j.get("company", {}).get("name", "") if isinstance(j.get("company"), dict) else "")
                    jobs.append({
                        "url": url,
                        "title": j.get("title", ""),
                        "company": company,
                        "source": "himalayas",
                        "salary": f"{j.get('minSalary','')} - {j.get('maxSalary','')}".strip(" -"),
                        "posted_at": j.get("postedAt", ""),
                        "raw_description": j.get("description", "")[:3000]
                    })
        except Exception as e:
            print(f"Himalayas error ({kw}): {e}")
        await asyncio.sleep(0.5)
    return jobs

async def fetch_wwr(session):
    jobs = []
    feeds = [
        "https://weworkremotely.com/categories/remote-programming-jobs.rss",
        "https://weworkremotely.com/categories/remote-devops-sysadmin-jobs.rss",
        "https://weworkremotely.com/categories/remote-marketing-jobs.rss",
        "https://weworkremotely.com/categories/remote-product-jobs.rss",
    ]
    for feed_url in feeds:
        try:
            async with session.get(feed_url) as r:
                text = await r.text()
                text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)
                root = ElementTree.fromstring(text)
                for item in root.findall(".//item"):
                    url = item.findtext("link") or ""
                    title = item.findtext("title") or ""
                    company = ""
                    if ": " in title:
                        parts = title.split(": ", 2)
                        company = parts[1] if len(parts) > 1 else ""
                        title = parts[2] if len(parts) > 2 else title
                    desc = item.findtext("description") or ""
                    soup = BeautifulSoup(desc, "html.parser")
                    jobs.append({
                        "url": url,
                        "title": title.strip(),
                        "company": company.strip(),
                        "source": "weworkremotely",
                        "salary": "",
                        "posted_at": item.findtext("pubDate") or "",
                        "raw_description": soup.get_text()[:3000]
                    })
        except Exception as e:
            print(f"WWR error ({feed_url}): {e}")
    return jobs

async def fetch_hn(session):
    jobs = []
    try:
        async with session.get("https://hn.algolia.com/api/v1/search?query=Ask+HN+Who+is+hiring&tags=story&hitsPerPage=5") as r:
            data = await r.json()
            hits = data.get("hits", [])
            thread = next((h for h in hits if "who is hiring" in h.get("title","").lower()), None)
            if not thread:
                return jobs
            story_id = thread["objectID"]
        async with session.get(f"https://hn.algolia.com/api/v1/search?tags=comment,story_{story_id}&hitsPerPage=200") as r:
            data = await r.json()
            for hit in data.get("hits", []):
                text = hit.get("comment_text", "") or ""
                if not text or "remote" not in text.lower():
                    continue
                soup = BeautifulSoup(text, "html.parser")
                plain = soup.get_text()
                link = soup.find("a")
                url = link["href"] if link and link.get("href") else f"https://news.ycombinator.com/item?id={hit.get('objectID','')}"
                jobs.append({
                    "url": url,
                    "title": plain[:100].strip(),
                    "company": "",
                    "source": "hackernews",
                    "salary": "",
                    "posted_at": datetime.fromtimestamp(hit.get("created_at_i", 0), tz=timezone.utc).isoformat(),
                    "raw_description": plain[:3000]
                })
    except Exception as e:
        print(f"HN error: {e}")
    return jobs

async def fetch_aijobs(session):
    jobs = []
    try:
        async with session.get("https://ai-jobs.net/jobs/", headers={"User-Agent": "Mozilla/5.0"}) as r:
            html = await r.text()
            soup = BeautifulSoup(html, "html.parser")
            for card in soup.select(".job-card, article.job, .job-listing, li.job"):
                title_el = card.select_one("h2, h3, .job-title, a")
                title = title_el.get_text(strip=True) if title_el else ""
                link = title_el.get("href", "") if title_el and title_el.name == "a" else ""
                if not link:
                    a = card.find("a")
                    link = a["href"] if a else ""
                if link and not link.startswith("http"):
                    link = "https://ai-jobs.net" + link
                company_el = card.select_one(".company, .company-name")
                company = company_el.get_text(strip=True) if company_el else ""
                desc_el = card.select_one(".description, .job-description, p")
                desc = desc_el.get_text(strip=True) if desc_el else ""
                if title:
                    jobs.append({
                        "url": link,
                        "title": title,
                        "company": company,
                        "source": "ai-jobs.net",
                        "salary": "",
                        "posted_at": "",
                        "raw_description": desc[:3000]
                    })
    except Exception as e:
        print(f"ai-jobs.net error: {e}")
    return jobs

async def fetch_workingnomads(session):
    jobs = []
    urls = [
        "https://www.workingnomads.com/remote-jobs?category=development",
        "https://www.workingnomads.com/remote-jobs?category=marketing",
        "https://www.workingnomads.com/remote-jobs?category=devops",
    ]
    for url in urls:
        try:
            async with session.get(url, headers={"User-Agent": "Mozilla/5.0"}) as r:
                html = await r.text()
                soup = BeautifulSoup(html, "html.parser")
                for card in soup.select("li.job, div.job, .job-item, article"):
                    title_el = card.select_one("h2, h3, .position, a.job-title")
                    title = title_el.get_text(strip=True) if title_el else ""
                    a = card.find("a")
                    link = a["href"] if a else ""
                    if link and not link.startswith("http"):
                        link = "https://www.workingnomads.com" + link
                    company_el = card.select_one(".company, .employer")
                    company = company_el.get_text(strip=True) if company_el else ""
                    if title:
                        jobs.append({
                            "url": link,
                            "title": title,
                            "company": company,
                            "source": "workingnomads",
                            "salary": "",
                            "posted_at": "",
                            "raw_description": (title + " " + company)[:3000]
                        })
        except Exception as e:
            print(f"WorkingNomads error ({url}): {e}")
    return jobs

async def fetch_dailyremote(session):
    jobs = []
    urls = [
        "https://dailyremote.com/remote-jobs?category=developer",
        "https://dailyremote.com/remote-jobs?category=marketing",
        "https://dailyremote.com/remote-jobs?category=devops",
    ]
    for url in urls:
        try:
            async with session.get(url, headers={"User-Agent": "Mozilla/5.0"}) as r:
                html = await r.text()
                soup = BeautifulSoup(html, "html.parser")
                for card in soup.select("article, .job-card, li.job"):
                    title_el = card.select_one("h2, h3, .title, a")
                    title = title_el.get_text(strip=True) if title_el else ""
                    a = card.find("a")
                    link = a["href"] if a else ""
                    if link and not link.startswith("http"):
                        link = "https://dailyremote.com" + link
                    company_el = card.select_one(".company, .employer, .organization")
                    company = company_el.get_text(strip=True) if company_el else ""
                    desc_el = card.select_one("p, .description")
                    desc = desc_el.get_text(strip=True) if desc_el else ""
                    if title:
                        jobs.append({
                            "url": link,
                            "title": title,
                            "company": company,
                            "source": "dailyremote",
                            "salary": "",
                            "posted_at": "",
                            "raw_description": (title + " " + desc)[:3000]
                        })
        except Exception as e:
            print(f"DailyRemote error ({url}): {e}")
    return jobs

async def fetch_remoteleaf(session):
    jobs = []
    try:
        async with session.get("https://remoteleaf.com/jobs/", headers={"User-Agent": "Mozilla/5.0"}) as r:
            html = await r.text()
            soup = BeautifulSoup(html, "html.parser")
            for card in soup.select("article, .job, .job-card, li"):
                title_el = card.select_one("h2, h3, .title, a")
                title = title_el.get_text(strip=True) if title_el else ""
                a = card.find("a")
                link = a["href"] if a else ""
                if link and not link.startswith("http"):
                    link = "https://remoteleaf.com" + link
                company_el = card.select_one(".company, .employer")
                company = company_el.get_text(strip=True) if company_el else ""
                desc_el = card.select_one("p, .description, .tags")
                desc = desc_el.get_text(strip=True) if desc_el else ""
                if title:
                    jobs.append({
                        "url": link,
                        "title": title,
                        "company": company,
                        "source": "remoteleaf",
                        "salary": "",
                        "posted_at": "",
                        "raw_description": (title + " " + desc)[:3000]
                    })
    except Exception as e:
        print(f"RemoteLeaf error: {e}")
    return jobs

def score_job(job):
    skills_str = "\n".join(f"- {s}" for s in SKILLS)
    prompt = f"""You are evaluating a remote job listing for a senior candidate based in Slovenia (EU timezone, CET/CEST).
The candidate has these skills:
{skills_str}

Job title: {job['title']}
Company: {job['company']}
Description: {job['raw_description'][:2000]}

The candidate is a hands-on builder and operator who ships real products end-to-end autonomously, and applies to roles that value builders, operators and AI-native generalists.

Score this job on 5 dimensions, each 1-10:
1. skill_match: how many of the candidate exact skills are required or valued
2. remote_friendliness: 10=worldwide no timezone req, 7=EU friendly, 4=flexible timezone, 1=US/specific timezone required — if job says "open to US candidates" or "residing in US" score 1
5. opportunity_quality: 10=early-stage AI startup or interesting product company, 5=average, 1=body shop/outsourcing/agency/large corp with bureaucracy

Weights: skill_match=0.30, remote_friendliness=0.25, seniority_fit=0.20, role_type_fit=0.15, opportunity_quality=0.10
Compute final_score = weighted average rounded to 1 decimal.

Respond ONLY in JSON no markdown:
{{"skill_match": 0, "remote_friendliness": 0, "seniority_fit": 0, "role_type_fit": 0, "opportunity_quality": 0, "final_score": 0.0, "matched_skills": [], "reason": "one sentence"}}"""

    for attempt in range(3):
        try:
            response = deepseek.messages.create(
                model="deepseek-v4-flash",
                max_tokens=600,
                thinking={"type": "disabled"},
                messages=[{"role": "user", "content": prompt}]
            )
            t = next((b.text for b in response.content if hasattr(b, "text")), "").strip()
            if not t:
                print(f"Empty response attempt {attempt+1}, retrying...")
                time.sleep(1)
                continue
            t = re.sub(r"```json|```", "", t).strip()
            t = re.sub(r'\n[ \t]*', ' ', t)
            result = json.loads(t)
            job["score"] = round(float(result.get("final_score", 0)), 1)
            job["matched_skills"] = result.get("matched_skills", [])
            job["reason"] = result.get("reason", "")
            return job
        except json.JSONDecodeError as e:
            print(f"JSON parse error attempt {attempt+1}: {e}")
            time.sleep(1)
        except Exception as e:
            print(f"Score error attempt {attempt+1} for '{job['title']}': {e}")
            time.sleep(1)

    job["score"] = 0
    job["matched_skills"] = []
    job["reason"] = ""
    return job

def get_existing_urls():
    try:
        import urllib.request
        req = urllib.request.Request(
            f"{SUPABASE_URL}/rest/v1/job_scout_results?select=url&limit=10000",
            headers={
                "apikey": SUPABASE_KEY,
                "Authorization": f"Bearer {SUPABASE_KEY}",
                "Accept": "application/json"
            }
        )
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read())
            return {row["url"] for row in data}
    except Exception as e:
        print(f"Failed to get existing URLs: {e}")
        return set()

def save_jobs(jobs, top_urls, run_id):
    if not jobs:
        return
    import urllib.request
    saved = 0
    for job in jobs:
        try:
            payload = json.dumps({
                "url": job["url"],
                "title": job["title"],
                "company": job["company"],
                "source": job["source"],
                "salary": job.get("salary", ""),
                "posted_at": job.get("posted_at") or None,
                "score": job.get("score", 0),
                "matched_skills": job.get("matched_skills", []),
                "raw_description": job.get("raw_description", "")[:5000],
                "reason": job.get("reason", ""),
                "is_top_pick": job["url"] in top_urls,
                "run_id": run_id
            }).encode()
            req = urllib.request.Request(
                f"{SUPABASE_URL}/rest/v1/job_scout_results",
                data=payload,
                headers={
                    "apikey": SUPABASE_KEY,
                    "Authorization": f"Bearer {SUPABASE_KEY}",
                    "Content-Type": "application/json",
                    "Prefer": "resolution=ignore-duplicates,return=minimal"
                },
                method="POST"
            )
            urllib.request.urlopen(req)
            saved += 1
        except Exception as e:
            print(f"Save error for '{job.get('title')}': {e}")
    print(f"Saved {saved}/{len(jobs)} jobs")

async def run():
    run_id = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M")
    print(f"[{run_id}] Job Scout starting...")

    async with aiohttp.ClientSession() as session:
        results = await asyncio.gather(
            fetch_remotive(session),
            fetch_remoteok(session),
            fetch_himalayas(session),
            fetch_wwr(session),
            fetch_hn(session),
            fetch_aijobs(session),
            fetch_workingnomads(session),
            fetch_dailyremote(session),
            fetch_remoteleaf(session),
        )

    all_jobs = []
    for batch in results:
        all_jobs.extend(batch)
    print(f"Fetched {len(all_jobs)} total jobs")

    location_ok = [j for j in all_jobs if is_location_friendly(j)]
    print(f"After location filter: {len(location_ok)} jobs")

    seen_urls = get_existing_urls()
    new_jobs = [j for j in location_ok if j["url"] and j["url"] not in seen_urls]
    print(f"New jobs to score: {len(new_jobs)}")

    scored = []
    for i, job in enumerate(new_jobs):
        if not job["title"]:
            continue
        job = score_job(job)
        scored.append(job)
        if (i + 1) % 10 == 0:
            print(f"Scored {i+1}/{len(new_jobs)}...")
        time.sleep(0.2)

    relevant = [j for j in scored if j.get("score", 0) >= 4]
    print(f"Relevant jobs (score >= 4): {len(relevant)}")

    # Deduplicate by title+company before picking top 10
    seen_tc = set()
    deduped = []
    for j in sorted(relevant, key=lambda x: x.get("score", 0), reverse=True):
        key = (j.get("title","").lower().strip(), j.get("company","").lower().strip())
        if key not in seen_tc:
            seen_tc.add(key)
            deduped.append(j)
    top10 = deduped[:10]
    top_urls = {j["url"] for j in top10}

    print("Top 10 this run:")
    for j in top10:
        print(f"  [{j['score']}] {j['title']} @ {j['company']} ({j['source']})")

    save_jobs(relevant, top_urls, run_id)
    print(f"[{datetime.now()}] Done.")

if __name__ == "__main__":
    if not os.environ.get("SKIP_WAIT"):
        now = datetime.now(timezone.utc)
        target = now.replace(hour=11, minute=0, second=0, microsecond=0)
        if now >= target:
            from datetime import timedelta
            target = target + timedelta(days=1)
        wait_seconds = (target - now).total_seconds()
        print(f"Waiting {wait_seconds/3600:.1f}h until 11:00 UTC...")
        time.sleep(wait_seconds)
    while True:
        asyncio.run(run())
        print(f"Sleeping {RUN_INTERVAL_HOURS}h...")
        time.sleep(RUN_INTERVAL_HOURS * 3600)
