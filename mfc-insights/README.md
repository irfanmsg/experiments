# mfc-insights

**ECC Contributor Analytics Dashboard** — A tech-lead-grade, 4-quarter engineering intelligence view for [`affaan-m/ECC`](https://github.com/affaan-m/ECC).

Zero build step. One HTML file + CSS + JS. Drop it in a browser or deploy to Vercel in 30 seconds.

---

## What it does

Renders 56 engineering insights across 11 categories for 8 contributors over 4 quarters (Q3 2025 → Q2 2026):

| Category | Insights |
|---|---|
| Velocity | Commit trajectory per contributor, team totals, growth leaders |
| Ship Speed | PRs/week per contributor, QoQ change |
| Cycle Time | PR open → merge latency, team average trend |
| QoQ Q3→Q4 | Quarter-on-quarter delta: commits, PRs, cycle time |
| QoQ Q4→Q1 | AI adoption crossover, complexity inflection |
| QoQ Q1→Q2 | Strongest quarter summary across all metrics |
| AI Adoption | Per-contributor AI tool usage %, team adoption curve, rollback correlation |
| Complexity | Cyclomatic complexity added/removed per contributor/quarter, hotspots |
| Releases | 18-release timeline, cadence, hotfix ratio |
| Rollbacks | 8 rollbacks mapped to contributor/quarter, AI-assisted rollback tracing |
| Productivity | LOC/commit ratio, PR merge rate, productivity score 0–100 |

---

## Files

```
mfc-insights/
├── dashboard.html       # Main page — section nav, KPI strip, all 12 panels
├── dashboard.css        # Design tokens, dark theme, component styles
├── dashboard.js         # DATA model + all render functions
├── fetch_ecc_data.sh    # GitHub API fetcher (needs GITHUB_TOKEN)
├── vercel.json          # Vercel static deployment config
├── SPEC.md              # Full technical specification
└── CLAUDE_CI_PROMPT.md  # Context document for resuming in a new Claude session
```

---

## Quick start

### Browser (local)

```bash
# From this directory
python3 -m http.server 8080
# Open http://localhost:8080/dashboard.html
```

Or just open `dashboard.html` directly in any modern browser — no server required.

### Vercel (one command)

```bash
npm i -g vercel
vercel --prod
```

`vercel.json` is pre-configured. The dashboard will be live at your Vercel project URL.

### SCP to local machine (headless server)

```bash
scp user@server:/path/to/mfc-insights/dashboard.{html,js,css} ~/Desktop/
```

---

## Live GitHub data

The `DATA` object in `dashboard.js` is modelled data. To replace it with live GitHub data:

```bash
export GITHUB_TOKEN=ghp_yourtoken
./fetch_ecc_data.sh        # writes ecc_data.json
```

Then wire `ecc_data.json` into the `DATA` constant in `dashboard.js`.

> **Rate limits**: unauthenticated GitHub API is 60 req/hr per IP. A token raises this to 5,000/hr.

---

## Design system

| Token | Value | Usage |
|---|---|---|
| `--accent` | `#e07856` | Claude coral — primary accent |
| `--bg-base` | `#0d0f14` | Page background |
| `--bg-surface` | `#13161e` | Card/panel background |
| `--q3` | `#fbbf24` | Q3 2025 — amber |
| `--q4` | `#60a5fa` | Q4 2025 — blue |
| `--q1` | `#34d399` | Q1 2026 — green |
| `--q2` | `#e07856` | Q2 2026 — coral |
| `--purple` | `#a78bfa` | AI adoption metrics |

---

## Terminal view

The full 56-insight table renders in the terminal via Node.js (ANSI colour):

```bash
node terminal-insights.js
```

Signal legend: `↑ Positive` · `⚠ Risk` · `◑ Watch` · `⬡ AI` · `ℹ Info`

---

## Tech stack

- **Vanilla HTML/CSS/JS** — zero dependencies, no build step
- **GitHub REST API** — contributors, commits, PRs, releases, code_frequency
- **Node.js** — terminal renderer (ANSI escape codes, box-drawing unicode)
- **Vercel** — optional static hosting via `@vercel/static`
- **Shell** — `fetch_ecc_data.sh` for live data ingestion

---

## Contributors

Built with Claude Code. Data modelled from the ECC repo structure (TypeScript 52%, Python 24%, Go 14%, Shell 10%) and public GitHub signals.
