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
# Events come from Ticketmaster, which rate-limits us now and then (429 → our 503 "busy"): that is theirs, not ours.
ev=$(curl -s -m 20 -w '\n%{http_code}' "$BASE/api/events?lat=48.86&lng=2.35&km=40&from=$(date -u +%F)T00:00:00&to=$(date -u +%F)T23:59:59"); evcode=${ev##*$'\n'}
if [ "$evcode" = 200 ] && grep -q '"items"' <<<"$ev"; then echo "ok   /api/events"; elif [ "$evcode" = 503 ] && grep -q busy <<<"$ev"; then echo "ok   /api/events (Ticketmaster busy, theirs)"; else echo "FAIL /api/events (got $evcode)"; fail=1; fi
check /api/pois?place=fr/paris   200 '"shelves"'
check /api/search?q=par          200 '"cities"'
check /api/stats                 200 '"places"'
check /sitemap.xml               200 'sitemap-cities.xml'
check /manifest.webmanifest      200 '"OuterView"'
check /city/fr/paris/feed.xml    200 '<feed xmlns'
check /es/city/es/madrid/feed.xml 200 'xml:lang="es"'
check /llms.txt                  200 '# OuterView'
check /ja/city/jp/tokyo/here     200 'watch=1'
check /api/airports?near=48.86,2.35 200 'CDG'
check /api/airports?iata=NRT      200 'Narita'
check /city/fr/paris/stay        200 'booking.com'
check /ja/city/jp/tokyo/fly      200 'HND'
check /es/city/es/madrid/do      200 'hacer en Madrid'
check /country/fr                200 'right now'
check /de/country/jp             200 'Japan jetzt'
# The app shell canary (docs/BLUEPRINT.md, section D): the home page must reference a main script that answers 200
# and is the real app (the hub's class name is in it), so a broken bundle fails the smoke and the uptime job.
main=$(curl -s -m 25 "$BASE/" | grep -o 'src="/assets/index-[A-Za-z0-9_-]*\.js"' | head -1 | sed 's/src="//;s/"$//')
if [ -z "$main" ]; then echo "FAIL app shell: no main script in /"; fail=1; else
  js=$(curl -s -m 25 -w '\n%{http_code}' "$BASE$main"); jscode=${js##*$'\n'}
  if [ "$jscode" = 200 ] && grep -q 'hub-wrap' <<<"$js"; then echo "ok   app shell $main"; else echo "FAIL app shell $main (got $jscode)"; fail=1; fi
fi
# The headless check, when a Chrome is on this machine (local deploys; CI skips it): the Board must render without
# a React error. This is what caught the render loop and the grid blowout on 2026-11-07.
CHROME=${CHROME:-$(ls -d /Users/*/Library/Caches/ms-playwright/chromium_headless_shell-*/chrome-headless-shell-mac-*/chrome-headless-shell 2>/dev/null | tail -1)}
if [ -n "$CHROME" ] && [ -x "$CHROME" ]; then
  prof=$(mktemp -d); log=$(mktemp)
  dom=$("$CHROME" --headless --disable-gpu --use-angle=swiftshader --enable-unsafe-swiftshader --no-first-run --user-data-dir="$prof" --timeout=30000 --virtual-time-budget=12000 --window-size=390,844 --enable-logging=stderr --v=0 --dump-dom "$BASE/place/48.857,2.352?shelf=stay&internal=1" 2>"$log")
  if grep -q 'Minified React error' "$log"; then echo "FAIL headless: React error on /place ($(grep -o 'Minified React error #[0-9]*' "$log" | head -1))"; fail=1
  elif ! grep -q 'data-shelf="stay"' <<<"$dom"; then echo "FAIL headless: the Board did not render on /place"; fail=1
  else echo "ok   headless: the Board renders, no React error"; fi
  rm -rf "$prof" "$log"
else echo "skip headless (no Chrome here)"; fi
# The news job must have run in the last 90 minutes (it runs every 15).
upd=$(curl -s -m 25 "$BASE/api/outer-index" | python3 -c "import json,sys,datetime; d=json.load(sys.stdin); t=datetime.datetime.fromisoformat(d['updated'].replace('Z','+00:00')); print(int((datetime.datetime.now(datetime.timezone.utc)-t).total_seconds()//60))" 2>/dev/null || echo 9999)
if [ "$upd" -gt 90 ]; then echo "FAIL news job: the index is $upd minutes old"; fail=1; else echo "ok   news job ran $upd min ago"; fi
exit $fail
