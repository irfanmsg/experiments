# Claude CI — Restart Prompt
## Project: ECC Contributor Analytics Dashboard
### affaan-m/ECC · Agent Harness OS

---

## CONTEXT SUMMARY

You are continuing work on a **GitHub contributor analytics dashboard** for the repo
`https://github.com/affaan-m/ECC` (Agent Harness OS — TypeScript/Python/Go/Shell).

The project lives at `/home/mirfan/mfc-insights/` on a headless Linux server (192.168.89.203).
GitHub is unreachable from this server (503/firewall), so all data is modelled from
README/API structure. Real data can be injected via `fetch_ecc_data.sh` once a
`GITHUB_TOKEN` is available.

---

## WHAT HAS BEEN BUILT

### Files
```
/home/mirfan/mfc-insights/
├── dashboard.html      # Main Claude-themed dark dashboard (493 lines)
├── dashboard.css       # Full stylesheet — Claude coral accent, dark mode (513 lines)
├── dashboard.js        # Data layer + all render functions (791 lines)
├── fetch_ecc_data.sh   # GitHub API fetcher script (needs GITHUB_TOKEN)
└── vercel.json         # Vercel static deployment config
```

### Dashboard Sections (dashboard.html)
1. **Sticky Header** — repo name, language badges, date range
2. **Section Nav Bar** — IntersectionObserver-driven active links
3. **KPI Strip** — 8 top-line metrics (commits, PRs, contributors, LOC, AI%, cycle time, complexity Δ, releases)
4. **Quarterly Velocity Matrix** (`#quarterly-section`) — per-contributor × 4-quarter table, sortable by Commits/PRs/LOC/CycleTime/ShipSpeed, with shipping speed heatmap
5. **QoQ Narrative Insights** (`#qoq-section`) — 3 insight cards (Q3→Q4, Q4→Q1, Q1→Q2) with wins, risks, actions, QoQ bar chart
6. **AI-Contributed Source Code** (`#ai-section`) — AI KPIs, per-contributor adoption table (Claude Code/Copilot/Cursor), module-level bars, adoption chart, insight panel
7. **Complexity Added/Removed** (`#complexity-section`) — per-contributor/quarter complexity delta table, waterfall chart, hotspot file list
8. **Weekly Commit Activity** — 52-week CSS bar chart (Q3'25→Q2'26)
9. **PR Analytics** — merge rate, cycle time, size distribution
10. **Release Frequency** — 18 releases across 4 quarters with timeline
11. **Rollback Tracker** — 8 rollback events with AI-assist flag
12. **Productivity Gain** — 6 velocity metrics vs Q3'25 baseline + AI synthesis insight

### Terminal Renderer (node inline scripts)
- Full ANSI-coloured contributor velocity table rendered in terminal
- Sections: Team Overview, Velocity, PR Cycle Time, AI Adoption, Complexity Delta, Productivity Leaderboard, AI Insights
- Shipping speed ASCII bar chart per contributor per quarter
- Velocity grade table (A/B/C/D)

---

## DATA MODEL (dashboard.js — DATA object)

### 4 Quarters
| Key | Period        |
|-----|---------------|
| q3  | Jul–Sep 2025  |
| q4  | Oct–Dec 2025  |
| q1  | Jan–Mar 2026  |
| q2  | Apr–Jun 2026  |

### 8 Contributors
| Login          | Role        | AI Tool         |
|----------------|-------------|-----------------|
| affaan-m       | Maintainer  | Claude Code     |
| ecs-dev1       | Core        | GitHub Copilot  |
| ecs-dev2       | Core        | Cursor          |
| agent-ops      | Ops         | GitHub Copilot  |
| ts-infra       | Infra       | Claude Code     |
| py-ml          | ML          | GitHub Copilot  |
| go-svc         | Backend     | Cursor          |
| docs-contrib   | Docs        | None            |

### Per-contributor quarterly fields
```js
quarterly[q] = { commits, prs, additions, deletions, cycleTime, shipSpeed, aiPct }
complexity[q] = { added, removed }   // cyclomatic complexity points
```

### Key Insights (as of Q2'26)
- Team commit velocity: +41% (Q3'25→Q2'26)
- PR cycle time: 3.4d → 2.1d (−38%)
- AI adoption: 12% → 38% team-wide
- @ts-infra highest AI rate: 68% (Claude Code)
- @ecs-dev2 highest velocity growth: +71% commits
- @go-svc only declining contributor (−22% commits, −35% ship speed)
- 8 rollbacks across 4Q — 2 traced to AI-generated concurrency code
- Net complexity REDUCED 18% Q3→Q2 (active refactoring Q1–Q2'26)
- 18 releases in 4Q (4+4+6+5 per quarter), 4 hotfixes

---

## DESIGN SYSTEM (dashboard.css)

```css
--bg-base:    #0d0f14   /* page background */
--bg-surface: #13161e   /* card background */
--accent:     #e07856   /* Claude coral */
--green:      #34d399
--yellow:     #fbbf24
--red:        #f87171
--blue:       #60a5fa
--cyan:       #22d3ee
--purple:     #a78bfa   /* AI features */

/* Quarter identity colours */
--q3: #fbbf24  /* amber  */
--q4: #60a5fa  /* blue   */
--q1: #34d399  /* green  */
--q2: #e07856  /* coral  */
```

Font stack: Inter UI / JetBrains Mono for code/numbers.
No external dependencies — pure HTML/CSS/JS, no build step.

---

## DEPLOYMENT

- **Local**: open `dashboard.html` directly in browser (all 3 files in same folder)
- **SCP**: `scp mirfan@192.168.89.203:/home/mirfan/mfc-insights/dashboard.{html,js,css} ~/Desktop/`
- **HTTP server**: `cd /home/mirfan/mfc-insights && python3 -m http.server 8080`
- **Vercel**: `vercel --name ecc-analytics-dashboard` from local machine (server firewall blocks outbound)
- **Vercel drag-drop**: vercel.com/new → "Deploy without Git" → drag folder

---

## REAL DATA INJECTION

```bash
export GITHUB_TOKEN=ghp_yourToken
cd /home/mirfan/mfc-insights
./fetch_ecc_data.sh        # produces ecc_data.json
# Then replace DATA object in dashboard.js with real values
```

GitHub API endpoints used:
- `/repos/affaan-m/ECC/stats/contributors` — quarterly commit/LOC breakdown
- `/repos/affaan-m/ECC/pulls?state=closed&base=main` — PR cycle times
- `/repos/affaan-m/ECC/commits?since=...` — commit history
- `/repos/affaan-m/ECC/releases` — release tags
- `/repos/affaan-m/ECC/stats/code_frequency` — weekly LOC adds/deletes

---

## PENDING / NEXT STEPS

Suggested improvements to implement next:

1. **Live GitHub data** — inject real API data via `fetch_ecc_data.sh` once token available
2. **Vercel deployment** — run from local machine, get live URL
3. **Export to PDF** — add print stylesheet trigger button
4. **Slack/email digest** — weekly cron that runs terminal renderer and posts insights
5. **Contributor drill-down** — click a contributor row → expand per-quarter PR list
6. **Complexity trend chart** — line chart per file showing complexity over 4 quarters
7. **AI code quality score** — ratio of AI LOC that survives vs gets reverted per contributor
8. **PR review network** — who reviews whose PRs (reviewer graph)

---

## HOW TO CONTINUE

To resume this project in a new Claude session, paste this entire file as your
first message, then state what you want to do next. Example continuations:

- "Add a Slack digest that posts the terminal velocity table weekly"
- "Add a contributor drill-down modal when clicking a table row"
- "Inject real GitHub data from ecc_data.json into dashboard.js"
- "Build a PDF export button"
- "Add a line chart for complexity trend per file"
- "Deploy to Vercel and give me the live URL"

---

*Generated: 2026-06-30 · Server: 192.168.89.203 · Project: /home/mirfan/mfc-insights/*
