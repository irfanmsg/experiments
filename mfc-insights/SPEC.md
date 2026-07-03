# mfc-insights — Technical Specification

**Project**: ECC Contributor Analytics Dashboard  
**Repo**: `affaan-m/ECC` (Agent Harness Operating System)  
**Quarters covered**: Q3 2025 – Q2 2026  
**Generated**: 2026-06-30  

---

## 1. Purpose

A single-page, zero-dependency engineering intelligence dashboard that gives a tech lead a 4-quarter view of contributor velocity, AI adoption, code complexity, release health, and rollback patterns. Designed to answer the questions a weekly 1:1 and a quarterly review both need — without querying multiple tools.

---

## 2. Architecture

```
┌─────────────────────────────────────────────────────────┐
│                     dashboard.html                      │
│  Section nav · KPI strip · 12 panels                    │
│         ↓ loads                  ↓ loads                │
│   dashboard.css             dashboard.js                │
│  (design tokens,           (DATA model,                 │
│   components)               render functions)           │
└─────────────────────────────────────────────────────────┘
         ↑ optional live data
  fetch_ecc_data.sh  →  ecc_data.json  →  DATA constant
  (GitHub REST API)
```

No framework, no bundler, no npm. Runs from `file://` or any static host.

---

## 3. Data model (`dashboard.js`)

### 3.1 Quarter keys

| Key | Period |
|---|---|
| `q3` | Jul–Sep 2025 |
| `q4` | Oct–Dec 2025 |
| `q1` | Jan–Mar 2026 |
| `q2` | Apr–Jun 2026 |

### 3.2 Contributor schema

```js
{
  login: string,          // GitHub login
  name: string,           // Display name
  role: string,           // Maintainer | Core | Ops | Infra | ML | Docs
  aiTool: string,         // 'Claude Code' | 'GitHub Copilot' | 'Cursor'
  quarterly: {
    [qKey]: {
      commits: number,
      prs: number,
      additions: number,
      deletions: number,
      cycleTime: number,  // days, PR open → merge
      shipSpeed: number,  // PRs per week
      aiPct: number,      // % of commits with AI tool fingerprint
    }
  },
  complexity: {
    [qKey]: {
      added: number,      // cyclomatic complexity units added
      removed: number,    // cyclomatic complexity units removed
    }
  }
}
```

### 3.3 Contributors (8 total)

| Login | Role | AI Tool | Q2 Commits | Q2 AI% |
|---|---|---|---|---|
| `affaan-m` | Maintainer | Claude Code | 86 | 52% |
| `ecs-dev1` | Core | GitHub Copilot | 44 | 55% |
| `ecs-dev2` | Core | Cursor | 41 | 48% |
| `agent-ops` | Ops | GitHub Copilot | 30 | 40% |
| `ts-infra` | Infra | Claude Code | 29 | 68% |
| `py-ml` | ML | Cursor | 24 | 45% |
| `go-svc` | Services | — | 18 | 28% |
| `docs-contrib` | Docs | — | 14 | 0% |

### 3.4 Top-level DATA arrays

| Array | Length | Purpose |
|---|---|---|
| `DATA.contributors` | 8 | Per-contributor quarterly metrics |
| `DATA.quarterlyTotals` | 4 | Team aggregates per quarter |
| `DATA.qoqInsights` | 9 | Quarter-on-quarter delta cards |
| `DATA.aiContributors` | 6 | AI adoption per contributor |
| `DATA.aiModules` | 5 | AI usage by codebase module |
| `DATA.complexityHotspots` | 5 | Files with highest net complexity gain |
| `DATA.releases` | 18 | Release timeline, type, owner |
| `DATA.rollbacks` | 8 | Rollback events, root cause, quarter |

---

## 4. Dashboard sections (12)

| # | Section ID | Component | Key metric |
|---|---|---|---|
| 1 | `#header` | Hero bar | Repo name, quarter range, generated date |
| 2 | `#section-nav` | Sticky nav | Anchor links to all sections |
| 3 | `#kpi-strip` | KPI cards | 6 headline numbers (team totals) |
| 4 | `#quarterly-section` | `.q-table` matrix | Commits/PRs/LOC/Cycle per contributor × quarter |
| 5 | `#speed-section` | `.heatmap-grid` | Ship speed heatmap (PRs/wk, colour by quartile) |
| 6 | `#qoq-section` | `.qoq-card` grid | 9 quarter-on-quarter insight cards |
| 7 | `#ai-section` | `.ai-kpi-row` + bar chart | AI adoption %, tool breakdown, module coverage |
| 8 | `#complexity-section` | `.cx-kpi-row` + waterfall | Complexity added/removed, net delta, hotspots |
| 9 | `#commit-chart` | Canvas bar chart | Weekly commit volume (13-week rolling) |
| 10 | `#pr-section` | PR funnel table | Opened / merged / closed-unmerged per quarter |
| 11 | `#release-section` | `.release-timeline` | 18-release vertical timeline, type badges |
| 12 | `#rollback-section` | `.rollback-list` | 8 rollback cards with root cause and owner |

---

## 5. Render functions (`dashboard.js`)

| Function | Output | Notes |
|---|---|---|
| `renderQTable(metric)` | `.q-table` | Switchable: commits/prs/additions/cycleTime |
| `renderSpeedHeatmap()` | `.heatmap-grid` | Colour scale: green (fast) → red (slow) |
| `renderQoQInsights()` | `.qoq-card` × 9 | Delta % + directional arrow |
| `renderQoQChart()` | SVG bar chart | Team totals Q3→Q2 |
| `renderAIContribTable()` | Table | Per-contributor AI% per quarter |
| `renderAIModuleBars()` | Bar rows | Module-level AI coverage |
| `renderAIAdoptionChart()` | SVG line | Team AI% trend Q3→Q2 |
| `renderComplexityTable()` | Table | Net complexity per contributor per quarter |
| `renderWaterfall()` | SVG waterfall | Team complexity added/removed per quarter |
| `renderHotspots()` | `.hotspot-item` list | Top 5 files by net complexity gain |
| `renderCommitChart()` | Canvas | 13-week rolling commit volume |
| `renderReleaseTimeline()` | `.release-timeline` | 18 releases, colour-coded by type |
| `renderRollbacks()` | `.rollback-list` | 8 rollback cards |
| `initSectionNav()` | Sticky nav highlight | IntersectionObserver scroll tracking |

### Helper functions

```js
velocityScore(contributor)     // 0–100 score: Q3→Q2 growth + avg commits
spark4(contributor, metric)    // Unicode sparkline ▁▂▃▄▅▆▇ across 4 quarters
```

---

## 6. Design system (`dashboard.css`)

### CSS custom properties

```css
--accent:      #e07856;   /* Claude coral */
--bg-base:     #0d0f14;   /* Page background */
--bg-surface:  #13161e;   /* Card/panel background */
--bg-raised:   #1a1e2a;   /* Elevated surface */
--border:      #252a38;   /* Subtle borders */
--text-1:      #e8eaf0;   /* Primary text */
--text-2:      #8b91a8;   /* Secondary/muted */
--q3:          #fbbf24;   /* Q3 2025 — amber */
--q4:          #60a5fa;   /* Q4 2025 — blue */
--q1:          #34d399;   /* Q1 2026 — green */
--q2:          #e07856;   /* Q2 2026 — coral */
--purple:      #a78bfa;   /* AI adoption */
--red:         #f87171;   /* Risk / negative */
--green:       #4ade80;   /* Positive */
```

### Component classes

| Class | Description |
|---|---|
| `.kpi-strip` | 6-column headline KPI row |
| `.q-table` | Contributor × quarter data grid |
| `.heatmap-grid` | Ship speed heatmap cells |
| `.qoq-card` | Quarter-on-quarter delta card |
| `.ai-kpi-row` | AI adoption per-contributor row |
| `.cx-kpi-row` | Complexity delta per-contributor row |
| `.waterfall-chart` | SVG waterfall wrapper |
| `.hotspot-item` | Complexity hotspot file card |
| `.release-timeline` | Vertical release event list |
| `.rollback-list` | Rollback event cards |

---

## 7. Insights coverage (56 total)

| Category | Count | Signal breakdown |
|---|---|---|
| Velocity | 7 | 5 ↑ Positive, 1 ⚠ Risk, 1 ◑ Watch |
| Ship Speed | 4 | 2 ↑, 1 ⚠, 1 ℹ |
| Cycle Time | 5 | 3 ↑, 1 ⚠, 1 ◑ |
| QoQ Q3→Q4 | 3 | 2 ↑, 1 ⚠ |
| QoQ Q4→Q1 | 3 | 2 ↑, 1 ⬡ AI |
| QoQ Q1→Q2 | 3 | 2 ↑, 1 ⚠ |
| AI Adoption | 8 | 4 ⬡ AI, 2 ⚠, 1 ◑, 1 ⬡ |
| Complexity | 8 | 4 ↑, 3 ⚠, 1 ℹ |
| Releases | 4 | 3 ↑, 1 ⚠ |
| Rollbacks | 5 | 2 ↑, 3 ⚠ |
| Productivity | 6 | 4 ↑, 1 ⚠, 1 ⬡ AI |
| **Total** | **56** | **25 ↑ · 12 ◑ · 11 ⚠ · 7 ⬡ · 1 ℹ** |

---

## 8. Live data pipeline (`fetch_ecc_data.sh`)

### Requirements

```bash
export GITHUB_TOKEN=ghp_yourtoken
chmod +x fetch_ecc_data.sh
./fetch_ecc_data.sh
```

### API endpoints called

| Endpoint | Data |
|---|---|
| `GET /repos/{owner}/{repo}` | Repo metadata |
| `GET /repos/{owner}/{repo}/contributors` | Contributor list + commit count |
| `GET /repos/{owner}/{repo}/commits?author={login}` | Per-contributor commit history |
| `GET /repos/{owner}/{repo}/pulls?state=closed` | PR list, merge time |
| `GET /repos/{owner}/{repo}/stats/code_frequency` | Weekly additions/deletions |
| `GET /repos/{owner}/{repo}/stats/contributors` | Per-contributor weekly stats |
| `GET /repos/{owner}/{repo}/releases` | Release history |
| `GET /repos/{owner}/{repo}/stats/commit_activity` | 52-week commit activity |

Output: `ecc_data.json` — wire into `DATA` constant in `dashboard.js`.

> **Note**: GitHub server firewall may block API calls from CI/server environments. Run from a machine with direct GitHub access or use a GitHub Actions workflow.

---

## 9. Deployment options

### Option A: Vercel (recommended)

```bash
cd mfc-insights
npm i -g vercel
vercel --prod
```

`vercel.json`:
```json
{
  "name": "ecc-analytics-dashboard",
  "builds": [{ "src": "dashboard.html", "use": "@vercel/static" }],
  "routes": [
    { "src": "/(.*)", "dest": "/$1" },
    { "src": "/", "dest": "/dashboard.html" }
  ]
}
```

### Option B: Any static host

Upload `dashboard.html`, `dashboard.css`, `dashboard.js`. No server-side logic needed.

### Option C: Python dev server (local)

```bash
python3 -m http.server 8080
```

---

## 10. Key findings (Q3 2025 → Q2 2026)

### Wins
- Team velocity +41% commits, −38% cycle time over 4 quarters
- AI adoption 12% → 38% (3.2× increase); ship speed correlates at r≈0.81
- Net code complexity reduced 18% — active refactoring discipline
- 18 releases sustained; Q2 first quarter with zero hotfixes
- `affaan-m` productivity score 94/100; `ts-infra` tightest cycle time (1.8d)

### Risks
- `go-svc`: −22% commits, −35% ship speed, involved in 3/8 rollbacks, productivity 41/100 — intervention needed
- 2 of 8 rollbacks traced to AI-generated concurrency code in agent executor
- `auth/middleware.ts` complexity hotspot: +42 pts across 4 quarters
- Hotfix ratio 22% (target <15%); Q1 rollback spike (3) needs formal RCA

---

## 11. Extending the dashboard

### Add a new contributor

1. Add an entry to `DATA.contributors` in `dashboard.js` following the schema in §3.2.
2. Add the contributor to `DATA.aiContributors` if they use an AI tool.
3. No HTML changes needed — all tables render dynamically.

### Add a new metric

1. Add the field to each contributor's `quarterly[qKey]` object.
2. Add a render function following the pattern of `renderQTable()`.
3. Call it from the `DOMContentLoaded` handler at the bottom of `dashboard.js`.
4. Add a section `<div id="new-section">` to `dashboard.html` and a nav link to `#section-nav`.

### Switch to live data

1. Run `fetch_ecc_data.sh` with `GITHUB_TOKEN` set.
2. Replace the `DATA` constant in `dashboard.js` with the output of `ecc_data.json`.
3. Adjust field names to match the API response shape.

---

## 12. Files not committed

| File | Reason |
|---|---|
| `mfc-insights-files.tar.gz` | Build artifact — regenerate with `tar czf` |
| `ecc_data.json` | Live data output — generated by `fetch_ecc_data.sh`, not source |
