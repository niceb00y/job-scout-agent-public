# Job Scout Agent

Autonomous remote job discovery agent for Vokrix. Runs daily, scrapes 9 job sources, scores every listing against a skills profile using DeepSeek, and saves relevant jobs to Supabase. Viewable via the Vokrix human dashboard.

---

## What it does

1. **Fetches** remote job listings from 9 sources in parallel
2. **Pre-filters** any job with location restrictions (US only, timezone locked, on-site, etc.) before scoring — saves LLM cost
3. **Scores** each remaining job on 5 dimensions using DeepSeek v4 Flash
4. **Saves** all relevant jobs (score >= 4) to Supabase, deduplicated by URL
5. **Flags** top 10 jobs per run as `is_top_pick`, deduplicated by title+company
6. **Sleeps** 24 hours and repeats

Runs daily at **11:00 UTC** (off-peak for DeepSeek API).

---

## Sources

| Source | Method | Categories |
|--------|--------|------------|
| remotive.com | Free public API | software-dev, devops-sysadmin, marketing, data |
| remoteok.com | Free public JSON API | all |
| himalayas.app | Free public API | keyword search: AI agent, LLM, Python, performance marketing, growth marketing, DevOps, AI automation |
| weworkremotely.com | Public RSS feeds | programming, devops, marketing, product |
| news.ycombinator.com | Algolia API (HN Who is Hiring thread) | remote-only comments |
| ai-jobs.net | HTML scrape | all |
| workingnomads.com | HTML scrape | development, marketing, devops |
| dailyremote.com | HTML scrape | developer, marketing, devops |
| remoteleaf.com | HTML scrape | all |

All Group 1 sources (remotive, remoteok, himalayas, WWR) are free public APIs — no keys, no signup, no scraping needed. HTML scrapers use BeautifulSoup with no proxies.

---

## Scoring

Each job is scored by DeepSeek v4 Flash on 5 dimensions (1-10 each):

| Dimension | Weight | What it measures |
|-----------|--------|-----------------|
| skill_match | 30% | How many candidate skills appear in the job |
| remote_friendliness | 25% | 10=worldwide, 7=EU friendly, 4=flexible timezone, 1=US/timezone locked |
| seniority_fit | 20% | 10=senior/lead/head/founding, 5=mid, 1=junior |
| role_type_fit | 15% | 10=AI/automation/growth/full-stack builder, 1=unrelated specialist |
| opportunity_quality | 10% | 10=well-funded AI startup, 1=body shop/agency |

**Final score** = weighted average, rounded to 1 decimal.

Jobs scoring >= 4 are saved. Top 10 per run are flagged `is_top_pick=true`, deduplicated by title+company so the same job from multiple sources only appears once.

LLM also outputs:
- `matched_skills` — which specific skills from the profile matched
- `reason` — one sentence explaining why the job is relevant

---

## Skills profile

The candidate profile used for scoring covers:

- **AI/Agents**: multi-agent system design, LLM integration, Anthropic API, DeepSeek, RAG, vector search, pgvector, Mem0, Zep, MCP server integration, agentic workflows, AI automation
- **Backend/DevOps**: Python, Docker, Railway, Coolify, Vercel, Traefik, GitHub Actions, CI/CD, Linux administration, REST API design
- **Data/Databases**: Supabase, PostgreSQL, MariaDB, data pipeline design, lead scoring, web scraping
- **Frontend**: Next.js, React, TypeScript, Vite, full-stack development
- **Marketing/Growth**: performance marketing, paid traffic, media buying, affiliate marketing, cold email, outreach automation, conversion optimization, SEO, AEO, B2B SaaS, GTM strategy, lead generation
- **Infrastructure**: Stripe, Cloudflare, DNS management, WordPress, email infrastructure (SPF/DKIM/DMARC)
- **Product/Business**: B2B SaaS product building, technical founder, venture studio operations, AI product management

---

## Location pre-filter

Before any LLM call, jobs are dropped if their title or description contains any of these phrases:

- us only, usa only, united states only, u.s. only
- must be located/reside/based in the us
- authorized to work in the us, us citizens only
- north america only, canada only, uk only, australia only
- est required, pst required, eastern/pacific time required
- must overlap with est/pst
- in-office, on-site, onsite required, not remote, no remote, hybrid only, local candidates only

Candidate is based in Slovenia (CET/CEST). Only worldwide or EU-friendly roles pass.

---

## Supabase schema

Table: `job_scout_results` in main Vokrix DB (``)

```sql
id            bigserial primary key
url           text unique not null
title         text
company       text
source        text
salary        text
posted_at     timestamptz
score         numeric
matched_skills text[]
raw_description text
reason        text
is_top_pick   boolean default false
run_id        text
created_at    timestamptz default now()
```

Deduplication is handled via `url` unique constraint + `Prefer: resolution=ignore-duplicates` on insert. 409 conflicts on save are expected and safe — they mean the same URL was found across multiple sources.

---

## Infrastructure

- **Deployed on**: Coolify, vokrix-agents project
- **Schedule**: runs at 11:00 UTC daily (off-peak DeepSeek hours)
- **Loop**: infinite while loop with 24h sleep between runs
- **Language**: Python 3.11
- **Dependencies**: aiohttp, beautifulsoup4, anthropic

### Env vars required

| Variable | Source |
|----------|--------|
| DEEPSEEK_API_KEY | .env |
| SUPABASE_URL | .env |
| SUPABASE_KEY | .env |

Optional: `SKIP_WAIT=true` — skips the 11:00 UTC wait for testing. Remove after testing.

---

## Dashboard

Results are visible in the Vokrix human dashboard under **[22] JOBS**.

Navigation:
- `j/k` — move up/down
- `Enter` — drill into run → see all jobs sorted by score
- `Enter` again — job detail: score, reason, matched skills, URL
- `o` — open job URL in browser
- `v` — copy selection
- `r` — refresh
- `q` — back / quit

Dashboard file: `jobs_dashboard.py`

---

## Repo structure

job-scout-agent/
├── job_scout.py # main agent
├── Dockerfile # python:3.11-slim, pip installs aiohttp beautifulsoup4 anthropic
└── README.md # this file


---

## Known issues

- WWR marketing RSS feed (`remote-marketing-jobs.rss`) has invalid XML characters and fails — other 3 WWR feeds work fine
- HTML scrapers (workingnomads, dailyremote, remoteleaf) may return 0 jobs if those sites change their HTML structure — APIs are the reliable sources
- First run after table wipe scores all ~474 jobs; subsequent runs only score new listings (dedup by URL)
