#!/bin/bash
# The smoke test: the pages and APIs that must answer, with a word each must contain. Run after every deploy
# (npm run deploy) and every 15 minutes by .github/workflows/uptime.yml. Exit 1 and say which failed.
BASE=${BASE:-https://outerview.world}
fail=0
check() { # path, expected status, a string the body must contain
  local body code
  body=$(curl -s -m 25 -A "OuterView smoke (https://outerview.world)" -w '\n%{http_code}' "$BASE$1")
  code=${body##*$'\n'}
  body=${body%$'\n'*}
  if [ "$code" != "$2" ] || ! grep -q -- "$3" <<<"$body"; then echo "FAIL $1 (got $code, wanted $2 with '$3')"; fail=1; else echo "ok   $1"; fi
}
check /                          200 '<div id="root"'
check /city/fr/paris             200 'Paris right now'
check /fr/city/fr/paris          200 'Paris en ce moment'
check /city/fr/paris/here        200 'Overture'
check /outer-index               200 'Outer Index'
check /api/outer-index           200 '"cities"'
check /api/weather?lat=48.86\&lng=2.35 200 '"tempC"'
check "/api/events?lat=48.86&lng=2.35&km=40&from=$(date -u +%F)T00:00:00&to=$(date -u +%F)T23:59:59" 200 '"items"'
check /api/pois?place=fr/paris   200 '"shelves"'
check /api/search?q=par          200 '"cities"'
check /api/stats                 200 '"places"'
check /sitemap.xml               200 'sitemap-cities.xml'
check /manifest.webmanifest      200 '"OuterView"'
# The news job must have run in the last 90 minutes (it runs every 15).
upd=$(curl -s -m 25 "$BASE/api/outer-index" | python3 -c "import json,sys,datetime; d=json.load(sys.stdin); t=datetime.datetime.fromisoformat(d['updated'].replace('Z','+00:00')); print(int((datetime.datetime.now(datetime.timezone.utc)-t).total_seconds()//60))" 2>/dev/null || echo 9999)
if [ "$upd" -gt 90 ]; then echo "FAIL news job: the index is $upd minutes old"; fail=1; else echo "ok   news job ran $upd min ago"; fi
exit $fail
