#!/usr/bin/env python3
"""OuterView news job: turn GDELT's newest 15-minute GKG files into small per-region story files.

Reads the English and the translated (every other language) GKG exports, keeps each document's title, outlet,
link, language, image and its first city-level location, and writes one JSON file per 10-degree tile with the
last 24 hours of stories. Headline and link only, never the article text. Data: GDELT Project (cite GDELT).

Usage: python3 gkg.py <out_dir>   (merges into the files already in out_dir)
"""
import html
import io
import json
import os
import re
import sys
import time
import urllib.request
import zipfile
from datetime import datetime, timedelta, timezone

LISTS = [
    ('https://data.gdeltproject.org/gdeltv2/lastupdate.txt', 'eng'),
    ('https://data.gdeltproject.org/gdeltv2/lastupdate-translation.txt', None),
]
KEEP_HOURS = 24
MAX_PER_TILE = 500
TITLE_RE = re.compile(r'<PAGE_TITLE>(.*?)</PAGE_TITLE>', re.S)
LANG_RE = re.compile(r'srclc:([a-z]{3})')
BAD_TITLE = re.compile(r'^(home|news|untitled|404|403|page not found|access denied)\b', re.I)
# Money news (money.json): GDELT marks each document with themes. One theme alone is noise (a crime story that
# names a bank), so a story counts as money news when its themes fall in two or more of these groups and at least
# one of them is a market group. Tested on live files 2026-11-11: about 1 story in 44.
MONEY = {
    'ECON_STOCKMARKET': 'mkt', 'ECON_IPO': 'mkt', 'ECON_EARNINGSREPORT': 'mkt',
    'ECON_INTEREST_RATES': 'rate', 'ECON_CENTRALBANK': 'rate', 'EPU_POLICY_CENTRAL_BANK': 'rate', 'WB_1235_CENTRAL_BANKS': 'rate',
    'ECON_INFLATION': 'infl', 'ECON_COST_OF_LIVING': 'infl',
    'ECON_HOUSING_PRICES': 'home',
    'ECON_DEBT': 'debt', 'ECON_BANKRUPTCY': 'debt',
    'ECON_BITCOIN': 'coin', 'ECON_GOLDPRICE': 'gold', 'ECON_CURRENCY_EXCHANGE_RATE': 'fx', 'ECON_OILPRICE': 'oil',
}
MONEY_CORE = {'mkt', 'rate', 'infl', 'fx', 'coin', 'gold'}
MONEY_PER_COUNTRY = 40
MONEY_MAX = 1500
NOT_TILES = ('state.json', 'index.json', 'top.json', 'launches.json', 'money.json')


def money_groups(themes):
    """V1Themes (THEME;THEME;...) to the sorted money groups, or [] when the story is not money news."""
    g = {MONEY[t] for t in themes.split(';') if t in MONEY}
    return sorted(g) if len(g) >= 2 and g & MONEY_CORE else []


def fetch(url, tries=3):
    for n in range(tries):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'OuterView news job (https://outerview.pages.dev)'})
            with urllib.request.urlopen(req, timeout=120) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001
            if n == tries - 1:
                raise
            time.sleep(5)


def gkg_url(list_url):
    text = fetch(list_url).decode('utf-8', 'replace')
    for line in text.splitlines():
        parts = line.split()
        if len(parts) == 3 and parts[2].endswith('.gkg.csv.zip'):
            return parts[2].replace('http://', 'https://')
    return None


def slots(url, back=8):
    """Files are announced before they are uploaded, and the translated ones lag an hour or more. So every run
    looks at the last `back` 15-minute slots and takes the ones it has not processed yet."""
    m = re.search(r'/(\d{14})\.', url)
    if not m:
        return [(url, url)]
    stamp = datetime.strptime(m.group(1), '%Y%m%d%H%M%S')
    out = []
    for n in range(back):
        t = (stamp - timedelta(minutes=15 * n)).strftime('%Y%m%d%H%M%S')
        out.append((t, url.replace(m.group(1), t)))
    return out


def load_state(out_dir):
    path = os.path.join(out_dir, 'state.json')
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except Exception:  # noqa: BLE001
        return {'done': []}


def save_state(out_dir, state):
    state['done'] = state['done'][-400:]
    with open(os.path.join(out_dir, 'state.json'), 'w', encoding='utf-8') as f:
        json.dump(state, f)


def tidy(s):
    s = html.unescape(s)
    s = re.sub(r'\s+', ' ', s).strip()
    s = re.sub(r'\s+([,.;:!?)\]])', r'\1', s)
    return s


def best_location(field):
    """V2Locations: Type#Name#CC#ADM1#ADM2#Lat#Lng#FeatureID#Offset;... Prefer the first city (3, 4), else any."""
    first = None
    for loc in field.split(';'):
        p = loc.split('#')
        if len(p) < 7:
            continue
        try:
            lat, lng = float(p[5]), float(p[6])
        except ValueError:
            continue
        if not (-90 <= lat <= 90 and -180 <= lng <= 180) or (lat == 0 and lng == 0):
            continue
        rec = {'name': p[1], 'cc': p[2], 'lat': round(lat, 3), 'lng': round(lng, 3), 'type': p[0]}
        if p[0] in ('3', '4'):
            return rec
        if first is None:
            first = rec
    return first


def tile_of(lat, lng):
    return f'{int(lat // 10) * 10}_{int(lng // 10) * 10}'


def parse(zip_bytes, default_lang):
    out = []
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
        name = z.namelist()[0]
        with z.open(name) as f:
            for raw in io.TextIOWrapper(f, encoding='utf-8', errors='replace'):
                cols = raw.rstrip('\n').split('\t')
                if len(cols) < 27:
                    continue
                m = TITLE_RE.search(cols[26])
                if not m:
                    continue
                title = tidy(m.group(1))
                if len(title) < 12 or BAD_TITLE.match(title):
                    continue
                loc = best_location(cols[10])
                if not loc:
                    continue
                lang = default_lang
                if not lang:
                    lm = LANG_RE.search(cols[25])
                    lang = lm.group(1) if lm else 'und'
                tone = cols[15].split(',')[0] if cols[15] else ''
                try:
                    tone = round(float(tone), 1)
                except ValueError:
                    tone = None
                row = {
                    'u': cols[4],
                    'd': cols[3],
                    't': title[:160],
                    'la': loc['lat'],
                    'lo': loc['lng'],
                    'pl': loc['name'][:80],
                    'cc': loc['cc'],
                    'ct': loc['type'],
                    'ts': cols[1],  # YYYYMMDDHHMMSS UTC
                    'lg': lang,
                    'im': cols[18][:300] if cols[18] else '',
                    'tn': tone,
                }
                groups = money_groups(cols[7])
                if groups:
                    row['mg'] = groups
                out.append(row)
    return out


def write_money(out_dir, stories, cutoff):
    """money.json: the last 24 hours of money news for the whole world, newest first, one row per headline, at
    most MONEY_PER_COUNTRY per country. Merges this run's stories into the file already there."""
    path = os.path.join(out_dir, 'money.json')
    old = []
    try:
        with open(path, encoding='utf-8') as f:
            old = json.load(f).get('s', [])
    except Exception:  # noqa: BLE001
        old = []
    fresh = [dict(s) for s in stories if s.get('mg')]  # copies: the tile rows keep their own outlet counts
    for s in fresh:
        s.pop('n', None)
        s.pop('ds', None)
    seen_url = set()
    by_title = {}
    merged = []
    for s in old + fresh:  # old first, so a headline keeps the count it already has
        if s['ts'] < cutoff or s['u'] in seen_url:
            continue
        seen_url.add(s['u'])
        key = re.sub(r'[^a-z0-9]+', ' ', s['t'].lower()).strip()[:70] or s['t'][:70]
        if key in by_title:
            first = by_title[key]
            outlets = first.setdefault('ds', [first['d']])
            if s['d'] not in outlets:
                first['n'] = first.get('n', 1) + 1
                if len(outlets) < 6:
                    outlets.append(s['d'])
            continue
        by_title[key] = s
        merged.append(s)
    merged.sort(key=lambda s: s['ts'], reverse=True)
    per = {}
    kept = []
    for s in merged:
        per[s['cc']] = per.get(s['cc'], 0) + 1
        if per[s['cc']] <= MONEY_PER_COUNTRY:
            kept.append(s)
    kept = kept[:MONEY_MAX]
    with open(path, 'w', encoding='utf-8') as f:
        json.dump({'updated': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'), 'source': 'GDELT', 's': kept}, f, ensure_ascii=False, separators=(',', ':'))
    return len(kept), len(per)


def main(out_dir):
    os.makedirs(out_dir, exist_ok=True)
    state = load_state(out_dir)
    done = set(state['done'])
    stories = []
    files = 0
    for list_url, lang in LISTS:
        url = gkg_url(list_url)
        if not url:
            print('no gkg url in', list_url)
            continue
        for stamp, u in slots(url):
            key = u.rsplit('/', 1)[-1]
            if key in done:
                continue
            try:
                data = fetch(u, tries=1)
            except Exception as e:  # noqa: BLE001
                print('not there yet', key, getattr(e, 'code', e))
                continue
            print('reading', key)
            stories += parse(data, lang)
            state['done'].append(key)
            files += 1
    print('files read:', files, '| stories with a title and a place:', len(stories))
    save_state(out_dir, state)

    cutoff = (datetime.now(timezone.utc) - timedelta(hours=KEEP_HOURS)).strftime('%Y%m%d%H%M%S')
    by_tile = {}
    for s in stories:
        by_tile.setdefault(tile_of(s['la'], s['lo']), []).append(s)

    # Merge with what is already on disk for the touched tiles, drop the old, dedupe by URL, cap by recency.
    written = 0
    for tile, fresh in by_tile.items():
        path = os.path.join(out_dir, f'{tile}.json')
        old = []
        if os.path.exists(path):
            try:
                with open(path, encoding='utf-8') as f:
                    old = json.load(f).get('s', [])
            except Exception:  # noqa: BLE001
                old = []
        # One row per story: the same headline from several outlets becomes one row that lists its outlets.
        seen_url = set()
        by_title = {}
        merged = []
        for s in fresh + old:
            if s['ts'] < cutoff or s['u'] in seen_url:
                continue
            seen_url.add(s['u'])
            key = re.sub(r'[^a-z0-9]+', ' ', s['t'].lower()).strip()[:70]
            if key in by_title:
                first = by_title[key]
                outlets = first.setdefault('ds', [first['d']])
                if s['d'] not in outlets and len(outlets) < 6:
                    outlets.append(s['d'])
                first['n'] = first.get('n', 1) + 1
                continue
            by_title[key] = s
            merged.append(s)
        merged.sort(key=lambda s: (s.get('n', 1) > 1, s['ts']), reverse=True)
        merged = merged[:MAX_PER_TILE]
        with open(path, 'w', encoding='utf-8') as f:
            json.dump({'tile': tile, 'updated': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'), 'source': 'GDELT', 's': merged}, f, ensure_ascii=False, separators=(',', ':'))
        written += 1

    # Tiles not touched this run still age: drop stories older than the window.
    for name in os.listdir(out_dir):
        if not name.endswith('.json') or name[:-5] in by_tile or name in NOT_TILES:
            continue
        path = os.path.join(out_dir, name)
        try:
            with open(path, encoding='utf-8') as f:
                d = json.load(f)
            kept = [s for s in d.get('s', []) if s['ts'] >= cutoff]
            if not kept:
                os.remove(path)
            elif len(kept) != len(d.get('s', [])):
                d['s'] = kept
                with open(path, 'w', encoding='utf-8') as f:
                    json.dump(d, f, ensure_ascii=False, separators=(',', ':'))
        except Exception:  # noqa: BLE001
            pass

    # The world right now: the stories most outlets carried in the last 24 hours, across every tile, with images.
    top = []
    for name in os.listdir(out_dir):
        if not name.endswith('.json') or name in NOT_TILES:
            continue
        try:
            with open(os.path.join(out_dir, name), encoding='utf-8') as f:
                for s in json.load(f).get('s', []):
                    if s.get('n', 1) >= 3:
                        top.append(s)
        except Exception:  # noqa: BLE001
            pass
    seen_titles = set()
    ranked = []
    for s in sorted(top, key=lambda s: (s.get('n', 1), s['ts']), reverse=True):
        key = re.sub(r'[^a-z0-9]+', ' ', s['t'].lower()).strip()[:60]
        if key in seen_titles:
            continue
        seen_titles.add(key)
        ranked.append(s)
        if len(ranked) >= 60:
            break
    with open(os.path.join(out_dir, 'top.json'), 'w', encoding='utf-8') as f:
        json.dump({'updated': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'), 'source': 'GDELT', 's': ranked}, f, ensure_ascii=False, separators=(',', ':'))

    with open(os.path.join(out_dir, 'index.json'), 'w', encoding='utf-8') as f:
        tiles = sorted(n[:-5] for n in os.listdir(out_dir) if n.endswith('.json') and n not in NOT_TILES)
        json.dump({'updated': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'), 'tiles': tiles, 'source': 'GDELT Project', 'license': 'cite GDELT; headline and link only'}, f)
    print('tiles written:', written, '| top stories:', len(ranked))
    try:
        rows, countries = write_money(out_dir, stories, cutoff)
        print('money stories:', rows, '| countries:', countries)
    except Exception as e:  # noqa: BLE001  (money news is extra: the tiles above are already written)
        print('money.json not written:', e)


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else 'tiles')
