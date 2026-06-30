/**
 * ECC Analytics Dashboard — affaan-m/ECC
 * Tech Lead View · 4-Quarter Analysis
 * Swap DATA with live GitHub API / git-log output when available.
 */

'use strict';

/* ════════════════════════════════════════════════════════════════
   DATA MODEL
   Quarters: Q3'25 = Jul–Sep 2025 | Q4'25 = Oct–Dec 2025
             Q1'26 = Jan–Mar 2026 | Q2'26 = Apr–Jun 2026
   ════════════════════════════════════════════════════════════════ */
const QUARTERS = ['Q3 \'25', 'Q4 \'25', 'Q1 \'26', 'Q2 \'26'];
const Q_KEYS   = ['q3', 'q4', 'q1', 'q2'];

const DATA = {
  meta: {
    repo: 'affaan-m/ECC',
    generatedAt: '2026-06-30',
    quarters: { q3: 'Jul–Sep 2025', q4: 'Oct–Dec 2025', q1: 'Jan–Mar 2026', q2: 'Apr–Jun 2026' },
  },

  /* ── Per-contributor quarterly breakdown ── */
  contributors: [
    {
      login: 'affaan-m', name: 'Affaan M', role: 'Maintainer',
      aiTool: 'Claude Code',
      quarterly: {
        q3: { commits: 58,  prs: 10, additions: 9800,  deletions: 2100, cycleTime: 3.2, shipSpeed: 0.77, aiPct: 8  },
        q4: { commits: 67,  prs: 12, additions: 11400, deletions: 2600, cycleTime: 2.8, shipSpeed: 0.92, aiPct: 22 },
        q1: { commits: 74,  prs: 14, additions: 13200, deletions: 3100, cycleTime: 2.4, shipSpeed: 1.08, aiPct: 35 },
        q2: { commits: 86,  prs: 16, additions: 16800, deletions: 3900, cycleTime: 1.9, shipSpeed: 1.23, aiPct: 52 },
      },
      complexity: {
        q3: { added: 82, removed: 14 },
        q4: { added: 74, removed: 22 },
        q1: { added: 58, removed: 41 },
        q2: { added: 31, removed: 68 },
      },
    },
    {
      login: 'ecs-dev1', name: 'Dev Contributor 1', role: 'Core',
      aiTool: 'GitHub Copilot',
      quarterly: {
        q3: { commits: 28,  prs: 6,  additions: 4800,  deletions: 1100, cycleTime: 3.8, shipSpeed: 0.46, aiPct: 14 },
        q4: { commits: 32,  prs: 7,  additions: 5600,  deletions: 1200, cycleTime: 3.1, shipSpeed: 0.54, aiPct: 28 },
        q1: { commits: 38,  prs: 9,  additions: 7100,  deletions: 1400, cycleTime: 2.6, shipSpeed: 0.69, aiPct: 41 },
        q2: { commits: 44,  prs: 11, additions: 8900,  deletions: 1800, cycleTime: 2.2, shipSpeed: 0.85, aiPct: 55 },
      },
      complexity: {
        q3: { added: 44, removed: 8  },
        q4: { added: 38, removed: 14 },
        q1: { added: 31, removed: 28 },
        q2: { added: 14, removed: 42 },
      },
    },
    {
      login: 'ecs-dev2', name: 'Dev Contributor 2', role: 'Core',
      aiTool: 'Cursor',
      quarterly: {
        q3: { commits: 24,  prs: 5,  additions: 4100,  deletions: 800,  cycleTime: 4.1, shipSpeed: 0.38, aiPct: 6  },
        q4: { commits: 28,  prs: 6,  additions: 4900,  deletions: 900,  cycleTime: 3.4, shipSpeed: 0.46, aiPct: 18 },
        q1: { commits: 35,  prs: 8,  additions: 6400,  deletions: 1100, cycleTime: 2.8, shipSpeed: 0.62, aiPct: 34 },
        q2: { commits: 41,  prs: 10, additions: 7900,  deletions: 1400, cycleTime: 2.3, shipSpeed: 0.77, aiPct: 48 },
      },
      complexity: {
        q3: { added: 38, removed: 6  },
        q4: { added: 34, removed: 11 },
        q1: { added: 24, removed: 22 },
        q2: { added: 12, removed: 38 },
      },
    },
    {
      login: 'agent-ops', name: 'Agent Ops', role: 'Ops',
      aiTool: 'GitHub Copilot',
      quarterly: {
        q3: { commits: 19,  prs: 4,  additions: 3200,  deletions: 1400, cycleTime: 3.6, shipSpeed: 0.31, aiPct: 10 },
        q4: { commits: 22,  prs: 5,  additions: 3800,  deletions: 1600, cycleTime: 3.0, shipSpeed: 0.38, aiPct: 19 },
        q1: { commits: 26,  prs: 6,  additions: 4600,  deletions: 1900, cycleTime: 2.5, shipSpeed: 0.46, aiPct: 31 },
        q2: { commits: 30,  prs: 7,  additions: 5400,  deletions: 2100, cycleTime: 2.1, shipSpeed: 0.54, aiPct: 40 },
      },
      complexity: {
        q3: { added: 29, removed: 18 },
        q4: { added: 26, removed: 21 },
        q1: { added: 22, removed: 24 },
        q2: { added: 8,  removed: 31 },
      },
    },
    {
      login: 'ts-infra', name: 'TS Infrastructure', role: 'Infra',
      aiTool: 'Claude Code',
      quarterly: {
        q3: { commits: 16,  prs: 3,  additions: 2900,  deletions: 700,  cycleTime: 3.3, shipSpeed: 0.23, aiPct: 20 },
        q4: { commits: 20,  prs: 4,  additions: 3600,  deletions: 800,  cycleTime: 2.8, shipSpeed: 0.31, aiPct: 38 },
        q1: { commits: 25,  prs: 5,  additions: 4500,  deletions: 900,  cycleTime: 2.2, shipSpeed: 0.38, aiPct: 54 },
        q2: { commits: 29,  prs: 6,  additions: 5200,  deletions: 1100, cycleTime: 1.8, shipSpeed: 0.46, aiPct: 68 },
      },
      complexity: {
        q3: { added: 24, removed: 9  },
        q4: { added: 20, removed: 14 },
        q1: { added: 16, removed: 18 },
        q2: { added: 8,  removed: 28 },
      },
    },
    {
      login: 'py-ml', name: 'Python ML', role: 'ML',
      aiTool: 'GitHub Copilot',
      quarterly: {
        q3: { commits: 14,  prs: 2,  additions: 2400,  deletions: 500,  cycleTime: 4.4, shipSpeed: 0.15, aiPct: 16 },
        q4: { commits: 17,  prs: 3,  additions: 2900,  deletions: 600,  cycleTime: 3.8, shipSpeed: 0.23, aiPct: 28 },
        q1: { commits: 20,  prs: 4,  additions: 3500,  deletions: 700,  cycleTime: 3.1, shipSpeed: 0.31, aiPct: 42 },
        q2: { commits: 23,  prs: 5,  additions: 4200,  deletions: 800,  cycleTime: 2.6, shipSpeed: 0.38, aiPct: 56 },
      },
      complexity: {
        q3: { added: 28, removed: 4  },
        q4: { added: 22, removed: 8  },
        q1: { added: 17, removed: 13 },
        q2: { added: 9,  removed: 21 },
      },
    },
    {
      login: 'go-svc', name: 'Go Services', role: 'Backend',
      aiTool: 'Cursor',
      quarterly: {
        q3: { commits: 18,  prs: 3,  additions: 2800,  deletions: 1200, cycleTime: 3.9, shipSpeed: 0.23, aiPct: 4  },
        q4: { commits: 16,  prs: 2,  additions: 2400,  deletions: 1100, cycleTime: 3.6, shipSpeed: 0.15, aiPct: 11 },
        q1: { commits: 12,  prs: 2,  additions: 1900,  deletions: 800,  cycleTime: 3.2, shipSpeed: 0.15, aiPct: 22 },
        q2: { commits: 14,  prs: 2,  additions: 2200,  deletions: 900,  cycleTime: 2.8, shipSpeed: 0.15, aiPct: 31 },
      },
      complexity: {
        q3: { added: 36, removed: 12 },
        q4: { added: 32, removed: 14 },
        q1: { added: 18, removed: 16 },
        q2: { added: 11, removed: 19 },
      },
    },
    {
      login: 'docs-contrib', name: 'Docs', role: 'Docs',
      aiTool: 'None',
      quarterly: {
        q3: { commits: 11,  prs: 1,  additions: 1100,  deletions: 400,  cycleTime: 2.1, shipSpeed: 0.08, aiPct: 0  },
        q4: { commits: 12,  prs: 2,  additions: 1300,  deletions: 500,  cycleTime: 1.9, shipSpeed: 0.15, aiPct: 5  },
        q1: { commits: 10,  prs: 1,  additions: 1100,  deletions: 400,  cycleTime: 1.8, shipSpeed: 0.08, aiPct: 8  },
        q2: { commits: 9,   prs: 1,  additions: 900,   deletions: 300,  cycleTime: 1.7, shipSpeed: 0.08, aiPct: 11 },
      },
      complexity: {
        q3: { added: 6,  removed: 2  },
        q4: { added: 5,  removed: 3  },
        q1: { added: 4,  removed: 4  },
        q2: { added: 2,  removed: 6  },
      },
    },
  ],

  /* ── Weekly commits (52 weeks, Q3'25→Q2'26) ── */
  weeklyCommits: [
    ['01 Jul',18,false],['08 Jul',24,false],['15 Jul',29,false],['22 Jul',22,false],['29 Jul',26,false],
    ['05 Aug',31,false],['12 Aug',28,false],['19 Aug',33,true], ['26 Aug',27,false],['02 Sep',24,false],
    ['09 Sep',30,false],['16 Sep',35,false],['23 Sep',29,false],['30 Sep',20,false],
    ['07 Oct',24,false],['14 Oct',32,false],['21 Oct',38,true], ['28 Oct',35,false],['04 Nov',29,false],
    ['11 Nov',34,false],['18 Nov',41,false],['25 Nov',36,false],['02 Dec',30,false],['09 Dec',27,false],
    ['16 Dec',22,false],['23 Dec',14,false],
    ['30 Dec',14,false],['06 Jan',22,false],['13 Jan',31,false],['20 Jan',28,false],['27 Jan',19,false],
    ['03 Feb',24,false],['10 Feb',33,true], ['17 Feb',41,false],['24 Feb',38,false],['03 Mar',27,false],
    ['10 Mar',35,false],['17 Mar',44,true], ['24 Mar',39,false],['31 Mar',29,false],
    ['07 Apr',31,false],['14 Apr',26,false],['21 Apr',38,false],['28 Apr',47,true],
    ['05 May',42,false],['12 May',36,false],['19 May',29,false],['26 May',33,false],
    ['02 Jun',28,false],['09 Jun',22,false],['16 Jun',19,false],['23 Jun',14,false],
  ],

  /* ── Quarterly team totals (for QoQ chart) ── */
  quarterlyTotals: [
    { q: 'Q3 \'25', commits: 312, prs: 56, additions: 64800, cycleTime: 3.4, aiPct: 12 },
    { q: 'Q4 \'25', commits: 356, prs: 68, additions: 78200, cycleTime: 2.9, aiPct: 23 },
    { q: 'Q1 \'26', commits: 409, prs: 78, additions: 94800, cycleTime: 2.4, aiPct: 35 },
    { q: 'Q2 \'26', commits: 441, prs: 96, additions:112400, cycleTime: 2.1, aiPct: 38 },
  ],

  /* ── QoQ Narrative insights ── */
  qoqInsights: [
    {
      from: 'Q3 \'25', to: 'Q4 \'25', label: 'Q3 → Q4',
      summary: 'Foundation quarter. Team shipped core agent harness and stabilised CI. Commit velocity +14%, PR throughput +21%. AI adoption increased from 12% to 23% — mainly Copilot onboarding for Python ML contributors.',
      topMover: { login: 'affaan-m', change: '+16%', metric: 'commits' },
      risk: { level: 'yellow', text: 'Cycle time still high (2.9d) and two rollbacks traced to large PRs >1k lines.' },
      wins: ['v1.0.0 stable release shipped', 'AgentShield integration merged', 'CI pipeline fully automated'],
      actions: ['Break large PRs', 'Enforce PR size limit <500 LOC', 'Start AI tooling pilot for TypeScript'],
    },
    {
      from: 'Q4 \'25', to: 'Q1 \'26', label: 'Q4 → Q1',
      summary: 'Acceleration quarter. Multi-language harness shipped for Go and Python. Highest rollback count (3) — traced to AI-generated concurrency code. Velocity +15%, but quality metrics dipped. MCP server pool merged mid-quarter.',
      topMover: { login: 'ecs-dev1', change: '+29%', metric: 'PRs merged' },
      risk: { level: 'red', text: '3 rollbacks in Q1 — highest single-quarter count. AI concurrency patterns require mandatory review gate.' },
      wins: ['Go + Python harness support', 'MCP server pool shipped', 'PR cycle time down to 2.4d'],
      actions: ['Add AI concurrency review checklist', 'Require load tests for AI-authored async code', 'Target <2 rollbacks in Q2'],
    },
    {
      from: 'Q1 \'26', to: 'Q2 \'26', label: 'Q1 → Q2',
      summary: 'Quality-and-scale quarter. Team applied Q1 learnings: smaller PRs, mandatory AI code reviews, active refactoring. Net complexity down 18%. Only 1 rollback. ECC Universal npm shipped. PR cycle time hit 2.1d — best in 4 quarters.',
      topMover: { login: 'ts-infra', change: '+68% AI rate', metric: 'AI-assist adoption' },
      risk: { level: 'green', text: 'Review response time crept up (6.8h). Team is shipping faster than review bandwidth allows.' },
      wins: ['ECC Universal npm released', 'Net complexity reduced 18%', 'AI-assist hits 38% team-wide', 'Only 1 rollback event'],
      actions: ['Expand review team bandwidth', 'Document AI code patterns in CONTRIBUTING.md', 'Target 2.0d cycle time in Q3\'26'],
    },
  ],

  /* ── AI contributions per contributor ── */
  aiContributors: [
    { login: 'affaan-m',   name: 'Affaan M',          tool: 'Claude Code',     q3: 8,  q4: 22, q1: 35, q2: 52, modules: ['harness/core', 'mcp/', 'hooks/'] },
    { login: 'ts-infra',   name: 'TS Infrastructure', tool: 'Claude Code',     q3: 20, q4: 38, q1: 54, q2: 68, modules: ['packages/', 'types/', 'sdk/'] },
    { login: 'ecs-dev1',   name: 'Dev Contributor 1', tool: 'GitHub Copilot',  q3: 14, q4: 28, q1: 41, q2: 55, modules: ['agent/', 'runtime/'] },
    { login: 'ecs-dev2',   name: 'Dev Contributor 2', tool: 'Cursor',          q3: 6,  q4: 18, q1: 34, q2: 48, modules: ['cli/', 'tools/'] },
    { login: 'py-ml',      name: 'Python ML',         tool: 'GitHub Copilot',  q3: 16, q4: 28, q1: 42, q2: 56, modules: ['python/', 'models/'] },
    { login: 'agent-ops',  name: 'Agent Ops',         tool: 'GitHub Copilot',  q3: 10, q4: 19, q1: 31, q2: 40, modules: ['ops/', 'deploy/'] },
    { login: 'go-svc',     name: 'Go Services',       tool: 'Cursor',          q3: 4,  q4: 11, q1: 22, q2: 31, modules: ['go/', 'services/'] },
    { login: 'docs-contrib',name:'Docs',              tool: 'None',            q3: 0,  q4: 5,  q1: 8,  q2: 11, modules: ['docs/'] },
  ],

  aiModules: [
    { name: 'harness/core',  lang: 'TypeScript', aiLoc: 28400, totalLoc: 52000, pct: 55 },
    { name: 'packages/ SDK', lang: 'TypeScript', aiLoc: 21800, totalLoc: 38000, pct: 57 },
    { name: 'python/',       lang: 'Python',     aiLoc: 18200, totalLoc: 44000, pct: 41 },
    { name: 'agent/runtime', lang: 'TypeScript', aiLoc: 16400, totalLoc: 36000, pct: 46 },
    { name: 'go/services',   lang: 'Go',         aiLoc: 11800, totalLoc: 31000, pct: 38 },
    { name: 'mcp/pool',      lang: 'TypeScript', aiLoc: 8200,  totalLoc: 17000, pct: 48 },
    { name: 'ops/deploy',    lang: 'Shell',      aiLoc: 4800,  totalLoc: 18000, pct: 27 },
  ],

  /* ── Complexity hotspots ── */
  complexityHotspots: [
    { file: 'src/harness/scheduler.ts',    q3Net: +28, q4Net: +22, q1Net: -18, q2Net: -31, language: 'TS'  },
    { file: 'src/agent/runtime.ts',        q3Net: +24, q4Net: +19, q1Net: -12, q2Net: -24, language: 'TS'  },
    { file: 'python/models/inference.py',  q3Net: +18, q4Net: +16, q1Net: +8,  q2Net: -14, language: 'PY'  },
    { file: 'go/services/pool.go',         q3Net: +22, q4Net: +18, q1Net: +2,  q2Net: -8,  language: 'GO'  },
    { file: 'src/mcp/server_pool.ts',      q3Net: +14, q4Net: +12, q1Net: -6,  q2Net: -19, language: 'TS'  },
  ],

  /* ── Releases (4Q) ── */
  releases: [
    { tag: 'v0.9.0', date: 'Jul 14 \'25', type: 'minor',  q: 'q3', desc: 'Pre-release: agent harness alpha',          prs: 12 },
    { tag: 'v0.9.1', date: 'Aug 02 \'25', type: 'patch',  q: 'q3', desc: 'Stability fixes for alpha runtime',          prs: 4  },
    { tag: 'v0.9.2', date: 'Sep 04 \'25', type: 'hotfix', q: 'q3', desc: 'Hotfix: memory leak in task pool',           prs: 2  },
    { tag: 'v0.9.3', date: 'Sep 22 \'25', type: 'patch',  q: 'q3', desc: 'Patch: env variable resolution edge cases',  prs: 5  },
    { tag: 'v1.0.0', date: 'Oct 18 \'25', type: 'major',  q: 'q4', desc: 'Stable release: core agent harness GA',      prs: 28 },
    { tag: 'v1.1.0', date: 'Nov 09 \'25', type: 'minor',  q: 'q4', desc: 'AgentShield + hooks API',                    prs: 14 },
    { tag: 'v1.1.1', date: 'Nov 21 \'25', type: 'hotfix', q: 'q4', desc: 'Hotfix: credential leak in env resolver',    prs: 3  },
    { tag: 'v1.2.0', date: 'Dec 14 \'25', type: 'minor',  q: 'q4', desc: 'Multi-language harness (Go, Python)',        prs: 18 },
    { tag: 'v1.2.1', date: 'Jan 19 \'26', type: 'hotfix', q: 'q1', desc: 'Hotfix: race condition in task scheduler',   prs: 2  },
    { tag: 'v1.3.0', date: 'Feb 08 \'26', type: 'minor',  q: 'q1', desc: 'MCP server pool + telemetry',                prs: 21 },
    { tag: 'v1.3.1', date: 'Feb 22 \'26', type: 'patch',  q: 'q1', desc: 'Patch: TypeScript strict mode fixes',        prs: 7  },
    { tag: 'v1.3.2', date: 'Mar 08 \'26', type: 'hotfix', q: 'q1', desc: 'Hotfix: auth token refresh loop',            prs: 1  },
    { tag: 'v1.4.0', date: 'Mar 28 \'26', type: 'minor',  q: 'q1', desc: 'Hooks v2 + async pipeline support',          prs: 16 },
    { tag: 'v1.4.1', date: 'Apr 12 \'26', type: 'patch',  q: 'q2', desc: 'Patch: go routine leak in pool manager',     prs: 4  },
    { tag: 'v1.5.0', date: 'Apr 30 \'26', type: 'minor',  q: 'q2', desc: 'ECC Universal npm — browser/node compat',   prs: 19 },
    { tag: 'v1.5.1', date: 'May 14 \'26', type: 'patch',  q: 'q2', desc: 'Patch: ESM interop fixes',                   prs: 6  },
    { tag: 'v1.5.2', date: 'May 31 \'26', type: 'hotfix', q: 'q2', desc: 'Hotfix: rate-limit retry storm',             prs: 2  },
    { tag: 'v1.6.0', date: 'Jun 18 \'26', type: 'minor',  q: 'q2', desc: 'AgentShield v2 + policy engine',             prs: 22 },
  ],

  /* ── Rollbacks (4Q) ── */
  rollbacks: [
    { id:'RB-001', q:'q3', date:'Aug 14 \'25', ref:'v0.9.1', author:'agent-ops',
      desc:'Memory leak in task pool caused OOM on long-running agents', cause:'Missing cleanup in task destructor',
      detectTime:'4.8h', rollbackTime:'62 min', aiAssisted: false },
    { id:'RB-002', q:'q3', date:'Sep 28 \'25', ref:'v0.9.3', author:'go-svc',
      desc:'Env variable resolution broke on nested template strings', cause:'Regex backtracking — O(2^n) worst case',
      detectTime:'2.1h', rollbackTime:'28 min', aiAssisted: false },
    { id:'RB-003', q:'q4', date:'Nov 21 \'25', ref:'v1.1.1', author:'affaan-m',
      desc:'Credential leak in env resolver caused auth failures in prod', cause:'Bad merge of feature/env-resolver',
      detectTime:'2.5h', rollbackTime:'38 min', aiAssisted: false },
    { id:'RB-004', q:'q4', date:'Dec 19 \'25', ref:'v1.2.0', author:'ecs-dev1',
      desc:'Go harness panicked on nil channel write under high concurrency', cause:'Missing nil-guard — AI-generated code',
      detectTime:'3.4h', rollbackTime:'44 min', aiAssisted: true },
    { id:'RB-005', q:'q1', date:'Jan 19 \'26', ref:'v1.2.1', author:'ecs-dev1',
      desc:'Race condition in task scheduler: worker starvation at >50 concurrent agents', cause:'Missing mutex — AI-generated concurrent scheduler',
      detectTime:'4.1h', rollbackTime:'52 min', aiAssisted: true },
    { id:'RB-006', q:'q1', date:'Feb 28 \'26', ref:'v1.3.0', author:'py-ml',
      desc:'Python inference model loaded into wrong memory tier — OOM on GPU node', cause:'Bad device mapping in AI-generated loader',
      detectTime:'3.8h', rollbackTime:'55 min', aiAssisted: false },
    { id:'RB-007', q:'q1', date:'Mar 10 \'26', ref:'v1.3.2', author:'affaan-m',
      desc:'Auth token refresh entered infinite retry loop on 429', cause:'Config drift — rate limit header not handled',
      detectTime:'3.0h', rollbackTime:'51 min', aiAssisted: false },
    { id:'RB-008', q:'q2', date:'May 31 \'26', ref:'v1.5.2', author:'ts-infra',
      desc:'Retry storm: exponential back-off missing jitter, hammered upstream at high concurrency',
      cause:'Missing jitter in retry implementation', detectTime:'2.2h', rollbackTime:'31 min', aiAssisted: false },
  ],
};

/* ════════════════════════════════════════════════════════════════
   HELPERS
   ════════════════════════════════════════════════════════════════ */
const fmt = {
  num:   (n) => n >= 1000 ? (n / 1000).toFixed(1) + 'k' : String(n),
  pct:   (n) => n + '%',
  delta: (a, b, invert = false) => {
    const d = ((b - a) / a * 100).toFixed(0);
    const pos = invert ? d < 0 : d > 0;
    const cls = d > 0 ? (invert ? 'red' : 'green') : (invert ? 'green' : 'red');
    return `<span class="${cls}">${d > 0 ? '↑' : '↓'} ${Math.abs(d)}%</span>`;
  },
  netDelta: (n) => {
    const cls = n < 0 ? 'green' : n > 0 ? 'red' : '';
    return `<span class="${cls}">${n > 0 ? '+' : ''}${n}</span>`;
  },
  score: (s) => {
    if (s >= 90) return { cls: 'score-a', label: 'A' };
    if (s >= 75) return { cls: 'score-b', label: 'B' };
    if (s >= 60) return { cls: 'score-c', label: 'C' };
    return { cls: 'score-d', label: 'D' };
  },
};

function initials(name) {
  return name.split(' ').map(w => w[0]).join('').slice(0, 2).toUpperCase();
}

function velocityScore(c) {
  const vals   = Q_KEYS.map(k => c.quarterly[k].commits);
  const growth = ((vals[3] - vals[0]) / vals[0]) * 100;
  const avg    = vals.reduce((a, b) => a + b, 0) / 4;
  return Math.min(99, Math.round(50 + growth * 0.4 + avg * 0.05));
}

function spark4(c, metric, invert = false) {
  const vals = Q_KEYS.map(k => c.quarterly[k][metric]);
  const max  = Math.max(...vals);
  const chars = ['▁','▂','▃','▄','▅','▆','▇'];
  return vals.map(v => {
    const idx = Math.round((v / max) * (chars.length - 1));
    const q   = vals.indexOf(v);
    const cls = q === vals.length - 1 ? 'spark-latest' : '';
    return `<span class="${cls}">${chars[idx]}</span>`;
  }).join('');
}

/* ════════════════════════════════════════════════════════════════
   QUARTERLY VELOCITY MATRIX
   ════════════════════════════════════════════════════════════════ */
const Q_METRIC_CONFIG = {
  commits:   { label: 'Commits',    subLabels: ['Count',''], fmt: (v) => v,          invert: false },
  prs:       { label: 'PRs',        subLabels: ['Merged',''], fmt: (v) => v,          invert: false },
  additions: { label: 'LOC Added',  subLabels: ['Lines',''],  fmt: (v) => fmt.num(v), invert: false },
  cycleTime: { label: 'Cycle Time', subLabels: ['Days',''],   fmt: (v) => v + 'd',    invert: true  },
  shipSpeed: { label: 'Ship Speed', subLabels: ['PRs/wk',''], fmt: (v) => v.toFixed(2),invert: false },
};

function renderQSubheaders(metric) {
  const row = document.getElementById('q-subheaders');
  if (!row) return;
  row.innerHTML = '<th></th>' + QUARTERS.map(q =>
    `<th class="q-sub">Val</th><th class="q-sub">QoQ</th>`
  ).join('') + '<th></th><th></th><th></th>';
}

function renderQTable(metric = 'commits') {
  renderQSubheaders(metric);
  const cfg   = Q_METRIC_CONFIG[metric];
  const tbody = document.getElementById('q-tbody');
  if (!tbody) return;

  const sorted = [...DATA.contributors].sort((a, b) => {
    return b.quarterly.q2[metric] - a.quarterly.q2[metric];
  });

  tbody.innerHTML = sorted.map((c, i) => {
    const vs   = Q_KEYS.map(k => c.quarterly[k][metric]);
    const qCells = vs.map((v, qi) => {
      const prev    = qi > 0 ? vs[qi - 1] : null;
      const deltaTd = prev !== null ? `<td class="q-delta">${fmt.delta(prev, v, cfg.invert)}</td>` : `<td class="q-delta">—</td>`;
      return `<td class="q-val mono">${cfg.fmt(v)}</td>${deltaTd}`;
    }).join('');

    const overallDelta = fmt.delta(vs[0], vs[3], cfg.invert);
    const vScore       = velocityScore(c);
    const sc           = fmt.score(vScore);
    const sparkHtml    = spark4(c, metric, cfg.invert);

    return `<tr>
      <td>
        <span class="contrib-avatar">${initials(c.name)}</span>
        <span class="contrib-name">${c.name}
          <span class="contrib-handle">@${c.login} · ${c.role}</span>
        </span>
      </td>
      ${qCells}
      <td class="trend-spark">${sparkHtml}</td>
      <td class="q-delta-overall">${overallDelta}</td>
      <td><span class="score-pill ${sc.cls}">${sc.label} · ${vScore}</span></td>
    </tr>`;
  }).join('');
}

function renderSpeedHeatmap() {
  const el = document.getElementById('speed-heatmap');
  if (!el) return;

  const max = Math.max(...DATA.contributors.flatMap(c =>
    Q_KEYS.map(k => c.quarterly[k].shipSpeed)
  ));

  const headers = `<div class="hm-row hm-header">
    <div class="hm-label">Contributor</div>
    ${QUARTERS.map(q => `<div class="hm-cell hm-head">${q}</div>`).join('')}
  </div>`;

  const rows = DATA.contributors.map(c => {
    const cells = Q_KEYS.map(k => {
      const v   = c.quarterly[k].shipSpeed;
      const pct = Math.round((v / max) * 100);
      const cls = pct >= 75 ? 'hm-hot' : pct >= 40 ? 'hm-warm' : 'hm-cool';
      return `<div class="hm-cell ${cls}" title="${QUARTERS[Q_KEYS.indexOf(k)]}: ${v} PRs/wk">${v.toFixed(2)}</div>`;
    }).join('');
    return `<div class="hm-row"><div class="hm-label">@${c.login}</div>${cells}</div>`;
  }).join('');

  el.innerHTML = headers + rows;
}

function initQTabs() {
  document.querySelectorAll('[data-qmetric]').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('[data-qmetric]').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      renderQTable(btn.dataset.qmetric);
    });
  });
}

/* ════════════════════════════════════════════════════════════════
   QoQ INSIGHTS
   ════════════════════════════════════════════════════════════════ */
function renderQoQInsights() {
  const el = document.getElementById('qoq-grid');
  if (!el) return;

  el.innerHTML = DATA.qoqInsights.map(ins => `
    <div class="qoq-card">
      <div class="qoq-card-header">
        <span class="qoq-label">${ins.label}</span>
        <span class="risk-dot risk-${ins.risk.level}"></span>
      </div>
      <p class="qoq-summary">${ins.summary}</p>
      <div class="qoq-mover">
        <span class="qm-icon">⬆</span>
        <span class="qm-text">Top mover: <strong>@${ins.topMover.login}</strong> ${ins.topMover.change} in ${ins.topMover.metric}</span>
      </div>
      <div class="qoq-risk risk-bg-${ins.risk.level}">
        <span class="risk-label">Risk:</span> ${ins.risk.text}
      </div>
      <div class="qoq-wins">
        <p class="qoq-section-label">Wins</p>
        ${ins.wins.map(w => `<div class="qoq-win-item">✓ ${w}</div>`).join('')}
      </div>
      <div class="qoq-actions">
        <p class="qoq-section-label">Actions for next quarter</p>
        ${ins.actions.map(a => `<div class="qoq-action-item">→ ${a}</div>`).join('')}
      </div>
    </div>
  `).join('');
}

function renderQoQChart() {
  const el = document.getElementById('qoq-chart');
  if (!el) return;

  const max  = Math.max(...DATA.quarterlyTotals.map(q => q.commits));
  const bars = DATA.quarterlyTotals.map((q, i) => {
    const pct = Math.round((q.commits / max) * 100);
    const cls = i === DATA.quarterlyTotals.length - 1 ? 'highlight' : '';
    return `<div class="chart-bar-wrap" title="${q.q}: ${q.commits} commits">
      <div class="chart-bar ${cls}" style="height:${pct}%" data-count="${q.commits}"></div>
      <span class="chart-bar-label">${q.q}<br>${q.commits}</span>
    </div>`;
  }).join('');

  el.innerHTML = bars;
}

/* ════════════════════════════════════════════════════════════════
   AI CONTRIBUTIONS
   ════════════════════════════════════════════════════════════════ */
function renderAIContribTable() {
  const tbody = document.getElementById('ai-contrib-tbody');
  if (!tbody) return;

  tbody.innerHTML = DATA.aiContributors.map(c => {
    const vals = [c.q3, c.q4, c.q1, c.q2];
    const max  = Math.max(...vals);
    const sparkHtml = vals.map(v => {
      const chars = ['▁','▂','▃','▄','▅','▆','▇'];
      const idx   = Math.round((v / (max || 1)) * (chars.length - 1));
      return chars[idx];
    }).join('');

    const toolCls = {
      'Claude Code':    'badge-accent',
      'GitHub Copilot': 'badge-blue',
      'Cursor':         'badge-cyan',
      'None':           '',
    }[c.tool] || '';

    return `<tr>
      <td>
        <span class="contrib-avatar">${initials(c.name)}</span>
        <span class="contrib-name">${c.name}
          <span class="contrib-handle">@${c.login}</span>
        </span>
      </td>
      <td><span class="badge ${toolCls}" style="font-size:0.65rem">${c.tool}</span></td>
      <td class="mono ai-pct-cell" data-pct="${c.q3}">${c.q3}%</td>
      <td class="mono ai-pct-cell" data-pct="${c.q4}">${c.q4}%</td>
      <td class="mono ai-pct-cell" data-pct="${c.q1}">${c.q1}%</td>
      <td class="mono ai-pct-cell" data-pct="${c.q2}">${c.q2}%</td>
      <td class="trend-spark">${sparkHtml}</td>
    </tr>`;
  }).join('');

  // Color AI pct cells
  document.querySelectorAll('.ai-pct-cell').forEach(td => {
    const v = parseInt(td.dataset.pct);
    if (v >= 50) td.style.color = 'var(--green)';
    else if (v >= 25) td.style.color = 'var(--yellow)';
    else if (v === 0) td.style.color = 'var(--text-muted)';
  });
}

function renderAIModuleBars() {
  const el = document.getElementById('ai-module-bars');
  if (!el) return;

  el.innerHTML = DATA.aiModules.map(m => {
    const barCls = m.lang === 'TypeScript' ? 'bar-blue' :
                   m.lang === 'Python'     ? 'bar-yellow' :
                   m.lang === 'Go'         ? 'bar-cyan' : 'bar-green';
    return `<div class="bar-row">
      <span class="bar-label" style="width:100px">${m.name}</span>
      <div class="bar-fill ${barCls}" style="width:${m.pct}%">${m.pct}%</div>
    </div>`;
  }).join('');
}

function renderAIAdoptionChart() {
  const el = document.getElementById('ai-adoption-chart');
  if (!el) return;

  const totals = DATA.quarterlyTotals;
  const max    = Math.max(...totals.map(q => q.aiPct));
  el.innerHTML = totals.map((q, i) => {
    const pct = Math.round((q.aiPct / max) * 100);
    const cls = i === totals.length - 1 ? 'highlight' : '';
    return `<div class="chart-bar-wrap" title="${q.q}: ${q.aiPct}% AI">
      <div class="chart-bar ${cls}" style="height:${pct}%"></div>
      <span class="chart-bar-label">${q.q}<br>${q.aiPct}%</span>
    </div>`;
  }).join('');
}

/* ════════════════════════════════════════════════════════════════
   COMPLEXITY DELTA
   ════════════════════════════════════════════════════════════════ */
function renderComplexityTable() {
  const tbody = document.getElementById('cx-tbody');
  if (!tbody) return;

  tbody.innerHTML = DATA.contributors.map(c => {
    let totalNet = 0;
    const qCells = Q_KEYS.map(k => {
      const { added, removed } = c.complexity[k];
      const net = added - removed;
      totalNet += net;
      return `
        <td class="mono red">+${added}</td>
        <td class="mono green">-${removed}</td>
        <td class="mono">${fmt.netDelta(net)}</td>`;
    }).join('');

    const sparkVals = Q_KEYS.map(k => c.complexity[k].added - c.complexity[k].removed);
    const maxV      = Math.max(...sparkVals.map(Math.abs), 1);
    const sparkHtml = sparkVals.map(v => {
      const chars = ['▁','▂','▃','▄','▅','▆','▇'];
      const idx   = Math.round((Math.abs(v) / maxV) * (chars.length - 1));
      return `<span class="${v < 0 ? 'green' : v > 10 ? 'red' : 'yellow'}">${chars[idx]}</span>`;
    }).join('');

    return `<tr>
      <td>
        <span class="contrib-avatar">${initials(c.name)}</span>
        <span class="contrib-name">${c.name}
          <span class="contrib-handle">@${c.login}</span>
        </span>
      </td>
      ${qCells}
      <td class="mono q-delta-overall">${fmt.netDelta(totalNet)}</td>
      <td class="trend-spark">${sparkHtml}</td>
    </tr>`;
  }).join('');
}

function renderWaterfall() {
  const el = document.getElementById('waterfall-chart');
  if (!el) return;

  const totals = DATA.quarterlyTotals;
  const nets   = DATA.contributors.reduce((acc, c) => {
    Q_KEYS.forEach((k, i) => {
      const { added, removed } = c.complexity[k];
      acc[i] = (acc[i] || 0) + (added - removed);
    });
    return acc;
  }, []);

  const absMax = Math.max(...nets.map(Math.abs), 1);

  el.innerHTML = `<div class="waterfall-bars">` +
    nets.map((net, i) => {
      const pct = Math.round((Math.abs(net) / absMax) * 80);
      const cls = net < 0 ? 'wf-down' : 'wf-up';
      return `<div class="wf-col">
        <div class="wf-val ${net < 0 ? 'green' : 'red'}">${net > 0 ? '+' : ''}${net}</div>
        <div class="wf-bar-wrap">
          <div class="wf-bar ${cls}" style="height:${pct}px"></div>
        </div>
        <div class="wf-label">${QUARTERS[i]}</div>
      </div>`;
    }).join('') +
  `</div>`;
}

function renderHotspots() {
  const el = document.getElementById('hotspot-list');
  if (!el) return;

  el.innerHTML = DATA.complexityHotspots.map(h => {
    const fourQNet = h.q3Net + h.q4Net + h.q1Net + h.q2Net;
    const langCls  = { TS: 'badge-blue', PY: 'badge-yellow', GO: 'badge-cyan' }[h.language] || '';
    return `<div class="hotspot-item">
      <span class="hotspot-file">${h.file}</span>
      <span class="badge ${langCls}">${h.language}</span>
      <div class="hotspot-qcells">
        ${[h.q3Net,h.q4Net,h.q1Net,h.q2Net].map((n,i) =>
          `<span class="hotspot-q ${n<0?'green':n>10?'red':'yellow'}" title="${QUARTERS[i]}">${n>0?'+':''}${n}</span>`
        ).join('')}
      </div>
      <span class="hotspot-total ${fourQNet<0?'green':'red'}">4Q: ${fourQNet>0?'+':''}${fourQNet}</span>
    </div>`;
  }).join('');
}

function initCxTabs() {
  document.querySelectorAll('[data-cmetric]').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('[data-cmetric]').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      // Future: filter table columns by added/removed/net
    });
  });
}

/* ════════════════════════════════════════════════════════════════
   COMMIT CHART (52 weeks)
   ════════════════════════════════════════════════════════════════ */
function renderCommitChart() {
  const container = document.getElementById('commitActivityChart');
  if (!container) return;

  const max  = Math.max(...DATA.weeklyCommits.map(w => w[1]));
  const bars = DATA.weeklyCommits.map(([label, count, highlight]) => {
    const pct = Math.round((count / max) * 100);
    return `<div class="chart-bar-wrap" title="${label}: ${count} commits">
      <div class="chart-bar${highlight ? ' highlight' : ''}" style="height:${pct}%"></div>
      <span class="chart-bar-label">${label.split(' ')[0]}</span>
    </div>`;
  }).join('');

  container.outerHTML = `<div class="css-chart" id="commitActivityChart">${bars}</div>`;
}

/* ════════════════════════════════════════════════════════════════
   RELEASE TIMELINE
   ════════════════════════════════════════════════════════════════ */
function renderReleaseTimeline() {
  const el = document.getElementById('release-timeline');
  if (!el) return;

  const qColors = { q3: '#fbbf24', q4: '#60a5fa', q1: '#34d399', q2: '#e07856' };
  el.innerHTML = DATA.releases.map(r => `
    <div class="release-item ${r.type}" style="border-left-color:${qColors[r.q] || 'var(--accent)'}">
      <span class="release-tag">${r.tag}</span>
      <span class="release-date">${r.date}</span>
      <span class="release-desc">${r.desc}</span>
      <span class="release-prs">${r.prs} PRs</span>
    </div>
  `).join('');
}

/* ════════════════════════════════════════════════════════════════
   ROLLBACK LIST
   ════════════════════════════════════════════════════════════════ */
function renderRollbacks() {
  const el = document.getElementById('rollback-list');
  if (!el) return;

  el.innerHTML = DATA.rollbacks.map(r => `
    <div class="rollback-item">
      <div class="rollback-header">
        <span class="rollback-id">${r.id} · ${r.ref}</span>
        <div style="display:flex;gap:0.5rem;align-items:center">
          ${r.aiAssisted ? '<span class="badge badge-purple" style="font-size:0.62rem">AI-code</span>' : ''}
          <span class="rollback-date">${r.date}</span>
        </div>
      </div>
      <p class="rollback-desc">${r.desc}</p>
      <div class="rollback-meta">
        <span>@${r.author}</span>
        <span>detect: ${r.detectTime}</span>
        <span>fix: ${r.rollbackTime}</span>
        <span>${r.cause}</span>
      </div>
    </div>
  `).join('');
}

/* ════════════════════════════════════════════════════════════════
   SECTION NAV HIGHLIGHT
   ════════════════════════════════════════════════════════════════ */
function initSectionNav() {
  const links    = document.querySelectorAll('.snav-link');
  const sections = [...links].map(l => document.querySelector(l.getAttribute('href'))).filter(Boolean);

  const obs = new IntersectionObserver(entries => {
    entries.forEach(e => {
      if (e.isIntersecting) {
        links.forEach(l => l.classList.remove('active'));
        const active = [...links].find(l => l.getAttribute('href') === '#' + e.target.id);
        if (active) active.classList.add('active');
      }
    });
  }, { threshold: 0.3 });

  sections.forEach(s => obs.observe(s));
}

/* ════════════════════════════════════════════════════════════════
   INIT
   ════════════════════════════════════════════════════════════════ */
function init() {
  // Quarterly matrix
  renderQTable('commits');
  renderSpeedHeatmap();
  initQTabs();

  // QoQ
  renderQoQInsights();
  renderQoQChart();

  // AI
  renderAIContribTable();
  renderAIModuleBars();
  renderAIAdoptionChart();

  // Complexity
  renderComplexityTable();
  renderWaterfall();
  renderHotspots();
  initCxTabs();

  // Charts & misc
  renderCommitChart();
  renderReleaseTimeline();
  renderRollbacks();
  initSectionNav();

  // Animate bar-fills
  setTimeout(() => {
    document.querySelectorAll('.bar-fill').forEach(bar => {
      const target = bar.style.width;
      bar.style.width = '0';
      setTimeout(() => {
        bar.style.width   = target;
        bar.style.transition = 'width 0.8s cubic-bezier(0.16,1,0.3,1)';
      }, 80);
    });
  }, 250);
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}
