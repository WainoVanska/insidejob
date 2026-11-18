# Sources (Phase 1 research)

Verified on **2026-11-18** with real, unauthenticated requests (User-Agent `insidejob-research/0.1`, ~1 req/s).
Job counts are what the endpoint returned that day. They are only there to show the endpoint is live.

Legend: ✅ usable (documented or official public feed) · ⚠️ works but awkward or undocumented · ❌ no clean source

## Company table

| Company | ATS / system | Identifier | Endpoint (tested) | Jobs | Status | Notes |
|---|---|---|---|---|---|---|
| NVIDIA (Helsinki) | Workday | `nvidia` / `wd5` / `NVIDIAExternalCareerSite` | `POST https://nvidia.wd5.myworkdayjobs.com/wday/cxs/nvidia/NVIDIAExternalCareerSite/jobs` | 2 for "intern Helsinki" | ⚠️ | Undocumented CXS JSON API (the one the career site itself uses). Server-side `searchText` + facets (`locationMainGroup`, `workerSubType`…). `postedOn` is relative text ("Posted 7 Days Ago"). robots.txt allows `/NVIDIAExternalCareerSite/` and doesn't mention `/wday/`. A Helsinki "System Software Engineering Intern – 2027" was live today. |
| Ericsson | Eightfold (PCSX) on top of SuccessFactors | `domain=ericsson.com` | `GET https://jobs.ericsson.com/api/pcsx/search?domain=ericsson.com&query=&location=Finland&start=0` | live | ⚠️ | Undocumented JSON. Fields: `name`, `locations`, `postedTs` (unix), `positionUrl`, `department`. robots.txt explicitly **allows** `/api/pcsx`. The older `/api/apply/v2/jobs` returns "Not authorized". The site uses invisible reCAPTCHA, but the API answered plain curl. Fragile, so treat it as best-effort. "Research Summer Interns: 6G Radio Networks" (Jorvas) was live today. |
| Nokia | Oracle Recruiting Cloud (HCM) | host `fa-evmr-saasfaprod1`, `siteNumber=CX_1` | `GET https://fa-evmr-saasfaprod1.fa.ocs.oraclecloud.com/hcmRestApi/resources/latest/recruitingCEJobRequisitions?onlyData=true&finder=findReqs;siteNumber=CX_1,keyword=intern,limit=25,sortBy=POSTING_DATES_DESC` | 230 total | ⚠️ | Undocumented-for-public but stable Oracle REST. Fields: `Id`, `Title`, `PrimaryLocation`, `PrimaryLocationCountry`, `PostedDate` (ISO date). `keyword` seems to match descriptions too, so filter client-side. Paginate with `offset`. Job URL: `https://jobs.nokia.com/en/sites/CX_1/job/{Id}`. No robots.txt on that host. |
| ICEYE | Ashby | `iceye` | `GET https://api.ashbyhq.com/posting-api/job-board/iceye` | 191 | ✅ | Documented public posting API. Fields: `title`, `location`, `secondaryLocations`, `publishedAt` (ISO), `jobUrl`, `employmentType`, `isRemote`, `workplaceType`. No server-side filter or pagination (one big response). |
| Smartly | Greenhouse | `smartlyio` | `GET https://boards-api.greenhouse.io/v1/boards/smartlyio/jobs` | 71 | ✅ | |
| Wolt | Greenhouse | `wolt` | `…/boards/wolt/jobs` | 184 (19 FI) | ✅ | Global board, so the location filter matters. |
| Supercell | Ashby | `supercell` | `…/job-board/supercell` | 30 | ✅ | |
| Remedy | Jobylon (embedded widget) | company id `2986` | `https://cdn.jobylon.com/jobs/companies/2986/embed/v2/?page_size=30` | n/a | ⚠️ | Returns an **HTML widget**, not JSON. Jobylon's JSON/XML feeds need a customer-issued hash. Jobylon's robots.txt blocks aggregator bots (Jobrapido, Jooble, Adzuna…). Don't parse the widget; leave this out of v1 or cover it via the Gmail source. (Greenhouse `remedy` is a *different* company, a US pharmacy.) |
| Housemarque | Greenhouse | `housemarque` | `…/boards/housemarque/jobs` | 5 | ✅ | |
| Rovio | Own WordPress site | n/a | `GET https://www.rovio.com/open-positions/feed/` (RSS) | 3 in feed | ⚠️ | Official WP RSS for the `open-positions` post type. pubDate + link + title. The feed may show only the latest N posts and location isn't a field (it's in the text). |
| Varjo | Workable | `varjo-1` | `GET https://apply.workable.com/api/v1/widget/accounts/varjo-1` | 2 | ✅ | Public widget JSON (the one Workable's own embed uses). Fields: `title`, `city`, `country`, `locations[]`, `published_on`, `url`, `shortcode`. robots.txt allows all. |
| Qt Group | Greenhouse | `theqtcompany` | `…/boards/theqtcompany/jobs` | 25 | ✅ | qt.io/open-positions is HubSpot on top of this board. Note the slug (`qt` is a US roofing company). Qt runs a "Finland Trainee Program". |
| Basemark | none | n/a | n/a | n/a | ❌ | Careers page lists ~1 role. Applications by email only. |
| Rightware | Deel Jobs | `jobs.deel.com/rightware` | n/a | n/a | ❌ | No documented public feed. Skip, or rely on Gmail alerts. |
| RELEX Solutions | Greenhouse | `relex` | `…/boards/relex/jobs` | 35 | ✅ | |
| Reaktor | Ashby | `reaktor` | `…/job-board/reaktor` | 13 | ✅ | |
| Futurice | Teamtailor (custom domain) | `careers.futurice.com` | `GET https://careers.futurice.com/jobs.rss` | 8 | ✅ | Officially documented Teamtailor RSS. Item: `title`, `link`, `pubDate`, `guid`, `remoteStatus`, `tt:locations/tt:location/{tt:city,tt:country}`, department. robots.txt allows `/jobs`. |
| Oura | Greenhouse | `oura` | `…/boards/oura/jobs` | 96 | ✅ | Titles contain non-ASCII, so force UTF-8 everywhere (bit me on Windows). |
| Aiven | Own site (Greenhouse behind it) | unknown | `https://aiven.io/careers/job` (HTML) | 44 | ⚠️ | Greenhouse-style IDs (`…101`) and they say recruiting mail comes from `eu.greenhouse.io`, but none of ~10 guessed board tokens worked. **TODO:** find the token from an apply link or ask Aiven. Until then, no clean source. |
| Supermetrics | Greenhouse | `supermetricsoy` (+ `supermetricsreferrals`) | `…/boards/supermetricsoy/jobs` | 9 (+1) | ✅ | EU-hosted board, but the normal `boards-api.greenhouse.io` serves it (`boards-api.eu…` doesn't resolve). |
| KONE | Workday | `kone` / `wd3` / `Careers` | `POST https://kone.wd3.myworkdayjobs.com/wday/cxs/kone/Careers/jobs` | 309 for "trainee" | ⚠️ | Same as NVIDIA. Search is fuzzy ("trainee" → "Field Trainer"), so filter client-side too. |
| Kuva Space | Teamtailor (custom domain) | `careers.kuvaspace.com` | `…/jobs.rss` | 2 | ✅ | |
| Metacore | none (links to Supercell careers) | n/a | n/a | n/a | ❌ | metacoregames.com's careers link goes to supercell.com/careers. No Metacore jobs found in Supercell's Ashby board today. Greenhouse `metacore` exists but is empty. |
| Small Giant | Greenhouse | `sggcareers` | `…/boards/sggcareers/jobs` | 4 | ✅ | |
| HypeHype | Teamtailor | `hypehype.teamtailor.com` | `…/jobs.rss` | 1 (open application) | ✅ | |
| Solita | Greenhouse | `solita` | `…/boards/solita/jobs` | 65 | ✅ | |
| Nitor | Workable | `nitor` | `…/widget/accounts/nitor` | 11 | ✅ | Finnish titles ("AI-arkkitehti"), so keywords need FI variants. |
| Siili | Teamtailor | `siili.teamtailor.com` | `…/jobs.rss` | 6 | ✅ | |
| Vincit | Teamtailor | `vincitoyj.teamtailor.com` | `…/jobs.rss` | 4 | ✅ | |
| Gofore | Own WordPress site | n/a | `GET https://gofore.com/en/careers/feed/` (RSS) | 10 | ✅ | Official WP RSS. robots.txt allows. Their old Teamtailor domain now redirects here. "Space Software Summer Trainee" was live today. Location isn't a structured field. |

## Coverage by source type

| Type | Companies | Count | API status |
|---|---|---|---|
| **Greenhouse** | Smartly, Wolt, Housemarque, RELEX, Qt, Oura, Supermetrics, Solita, Small Giant (+ Aiven once the token is found) | **9** | Documented, no auth ("Job Board data is publicly available"). `?content=true` adds description, departments, offices. No server-side filter or pagination. |
| **Teamtailor RSS** | Futurice, Kuva Space, HypeHype, Siili, Vincit | **5** | Official feed (Teamtailor help: add `.rss` to the jobs page). The REST API needs a company key, so it's not for us. |
| **Generic RSS (WordPress)** | Gofore, Rovio | **2** | Official site feeds. |
| **Ashby** | ICEYE, Supercell, Reaktor | **3** | Documented posting API, no auth shown. Docs frame it as "for your own careers page", with no rate limits or terms stated. |
| **Workable** | Varjo, Nitor | **2** | Public widget endpoint (undocumented but meant for embedding). |
| **Workday** | NVIDIA, KONE | **2** | Undocumented CXS API. Very common among big companies. |
| Oracle HCM | Nokia | 1 | Undocumented. |
| Eightfold | Ericsson | 1 | Undocumented, robots-allowed. |
| ❌ / skip | Remedy (Jobylon), Rightware (Deel), Basemark (email), Metacore (none), Aiven (pending) | 5 | Gmail alerts can cover these later. |

## Recommendation: first adapters

1. **Greenhouse**: 9 companies, documented public API, the simplest JSON. Start here.
2. **RSS, with a Teamtailor extension**: one adapter covers 7 companies (5 Teamtailor plus Gofore and Rovio). Parse the standard RSS fields, and read `tt:location` when present for structured location.
3. **Ashby**: 3 high-value companies (ICEYE, Supercell, Reaktor), trivial JSON.

Together these cover **19 of 30** companies with sources that are documented or official feeds.

The strong 4th is **Workday**. NVIDIA and KONE matter a lot for internships, and Workday also unlocks many other large employers (e.g. Nordea, Wärtsilä, ABB often use it). It's undocumented, so build it after the pipeline is stable. Workable (2) is a cheap 5th.

## Politeness and legal notes

- No HTML scraping anywhere above. Every ✅/⚠️ source is a JSON/RSS endpoint served by the ATS or the company for listing its own jobs.
- robots.txt checked: Greenhouse API (only `/embed/` disallowed), Workable (allow all), Teamtailor (only `/app/`, `/messages/`, `/jobs/internal/` disallowed, and `aihitdata` bot blocked), NVIDIA Workday (career site allowed), Ericsson (explicitly allows `/api/pcsx`), Gofore (allow). Ashby API, Oracle HCM and rovio.com have no robots.txt.
- For the undocumented ones (Workday, Oracle, Eightfold): hourly or less, one request per board per run, proper UA with a contact URL (the repo URL, not an email), and stop on 4xx/429.
- Greenhouse and Ashby boards are one unpaginated response per company, so that's one request per company per run.
