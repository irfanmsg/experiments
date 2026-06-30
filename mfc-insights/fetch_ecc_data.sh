#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════════
#  ECC GitHub Analytics Fetcher — affaan-m/ECC
#  Usage: GITHUB_TOKEN=ghp_xxx ./fetch_ecc_data.sh
#  Outputs: ecc_data.json  (populate DATA object in dashboard.js)
# ══════════════════════════════════════════════════════════════════
set -euo pipefail

REPO="affaan-m/ECC"
SINCE="2025-12-30T00:00:00Z"
OUT="ecc_data.json"

if [[ -z "${GITHUB_TOKEN:-}" ]]; then
  echo "❌ Set GITHUB_TOKEN before running this script."
  echo "   export GITHUB_TOKEN=ghp_yourTokenHere"
  exit 1
fi

AUTH_HEADER="Authorization: Bearer $GITHUB_TOKEN"
API="https://api.github.com"

api() { curl -sS -H "$AUTH_HEADER" -H "Accept: application/vnd.github+json" "$@"; }

echo "⟳ Fetching repo metadata…"
REPO_INFO=$(api "$API/repos/$REPO")

echo "⟳ Fetching contributors…"
CONTRIBUTORS=$(api "$API/repos/$REPO/contributors?per_page=100")

echo "⟳ Fetching contributor stats (may take a moment)…"
CONTRIB_STATS="null"
for i in 1 2 3; do
  RESP=$(api "$API/repos/$REPO/stats/contributors")
  if echo "$RESP" | python3 -c "import sys,json; data=json.load(sys.stdin); assert isinstance(data, list)" 2>/dev/null; then
    CONTRIB_STATS="$RESP"
    break
  fi
  echo "   GitHub still computing stats, retry $i/3…"
  sleep 3
done

echo "⟳ Fetching PRs merged to main (last 6 months)…"
PRS_P1=$(api "$API/repos/$REPO/pulls?state=closed&base=main&per_page=100&page=1")
PRS_P2=$(api "$API/repos/$REPO/pulls?state=closed&base=main&per_page=100&page=2")

echo "⟳ Fetching commits since $SINCE…"
COMMITS_P1=$(api "$API/repos/$REPO/commits?since=$SINCE&per_page=100&page=1")
COMMITS_P2=$(api "$API/repos/$REPO/commits?since=$SINCE&per_page=100&page=2")
COMMITS_P3=$(api "$API/repos/$REPO/commits?since=$SINCE&per_page=100&page=3")

echo "⟳ Fetching releases…"
RELEASES=$(api "$API/repos/$REPO/releases?per_page=100")

echo "⟳ Fetching branches…"
BRANCHES=$(api "$API/repos/$REPO/branches")

echo "⟳ Fetching weekly code frequency…"
CODE_FREQ=$(api "$API/repos/$REPO/stats/code_frequency")

echo "⟳ Fetching weekly commit activity…"
COMMIT_ACTIVITY=$(api "$API/repos/$REPO/stats/commit_activity")

echo "⟳ Fetching language breakdown…"
LANGUAGES=$(api "$API/repos/$REPO/languages")

echo "⟳ Fetching issues…"
ISSUES=$(api "$API/repos/$REPO/issues?state=all&per_page=100")

echo "⟳ Writing $OUT…"
python3 - <<PYEOF
import json, sys

def safe(raw):
    try:
        return json.loads(raw) if isinstance(raw, str) else raw
    except Exception:
        return None

data = {
    "meta": {
        "repo": "$REPO",
        "generatedAt": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
        "windowStart": "$SINCE",
    },
    "repo":            safe('''$REPO_INFO'''),
    "contributors":    safe('''$CONTRIBUTORS'''),
    "contrib_stats":   safe('''$CONTRIB_STATS'''),
    "prs_page1":       safe('''$PRS_P1'''),
    "prs_page2":       safe('''$PRS_P2'''),
    "commits_page1":   safe('''$COMMITS_P1'''),
    "commits_page2":   safe('''$COMMITS_P2'''),
    "commits_page3":   safe('''$COMMITS_P3'''),
    "releases":        safe('''$RELEASES'''),
    "branches":        safe('''$BRANCHES'''),
    "code_frequency":  safe('''$CODE_FREQ'''),
    "commit_activity": safe('''$COMMIT_ACTIVITY'''),
    "languages":       safe('''$LANGUAGES'''),
    "issues":          safe('''$ISSUES'''),
}

with open("$OUT", "w") as f:
    json.dump(data, f, indent=2)

print(f"✅ Saved {len(json.dumps(data))} bytes → $OUT")
PYEOF

echo ""
echo "Next: paste ecc_data.json values into the DATA object in dashboard.js"
echo "Done."
