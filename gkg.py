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
# Politics news (politics.json): the same idea, with a tighter test, because GDELT marks the whole article and
# most long articles name a president or a government somewhere. A story counts as politics when
#   1. its themes fall in two or more of the core groups (a vote, a party, a law or a lawmaker),
#   2. and in three or more groups in all,
#   3. and a core mark sits in the first POL_EARLY characters of the article (it opens on politics),
#   4. and core marks are at least POL_SHARE of all the marks in it (it stays on politics).
# Tested on live files 2026-11-11 (the week of the US midterms): about 1 story in 21; rules 3 and 4 dropped the
# stories that only pass through politics (a business deal, a flood, a column about something else).
# Nobody picks stories and no outlet is ranked or rated: the test reads GDELT's marks and nothing else.
POLITICS = {
    'ELECTION': 'vote',
    'EPU_POLICY_POLITICAL': 'party',
    'LEGISLATION': 'law', 'EPU_POLICY_LEGISLATION': 'law', 'EPU_POLICY_CONGRESS': 'law', 'EPU_POLICY_CONGRESSIONAL': 'law',
    'EPU_POLICY_LAWMAKERS': 'law', 'CONSTITUTIONAL': 'law', 'TAX_FNCACT_LAWMAKER': 'law', 'TAX_FNCACT_LAWMAKERS': 'law',
    'TAX_FNCACT_SENATOR': 'law', 'TAX_FNCACT_SENATORS': 'law', 'TAX_FNCACT_CONGRESSMAN': 'law', 'TAX_FNCACT_LEGISLATORS': 'law',
    'TAX_FNCACT_PRIME_MINISTER': 'gov', 'TAX_FNCACT_MINISTER': 'gov', 'TAX_FNCACT_MINISTERS': 'gov', 'TAX_FNCACT_PRESIDENT': 'gov',
    'GENERAL_GOVERNMENT': 'gov', 'EPU_POLICY_GOVERNMENT': 'gov', 'TAX_FNCACT_GOVERNOR': 'gov', 'TAX_FNCACT_VICE_PRESIDENT': 'gov',
    'PROTEST': 'unrest', 'POLITICAL_TURMOIL': 'unrest', 'IMPEACHMENT': 'unrest', 'SCANDAL': 'unrest', 'CORRUPTION': 'unrest',
    'WB_2473_DIPLOMACY_AND_NEGOTIATIONS': 'world', 'SANCTIONS': 'world', 'TAX_FNCACT_FOREIGN_MINISTER': 'world',
    'TAX_FNCACT_DIPLOMAT': 'world', 'TAX_FNCACT_DIPLOMATS': 'world',
}
POL_PARTY = 'TAX_POLITICAL_PARTY'  # every party mark starts with this (TAX_POLITICAL_PARTY_DEMOCRATS, ...)
POL_CORE = {'vote', 'party', 'law'}
POL_EARLY = 700
POL_SHARE = 0.05
POL_PER_COUNTRY = 40  # half of them the stories most outlets carry, half the newest
POL_MAX = 1500
# One story, every outlet: a row carried by several outlets names up to OUTLETS of them (ds), each with its own
# link (us, in the same order) and the country it is based in (dc, in the same order, '' when not known).
OUTLETS = 40
# A country's own file (country/<cc>.json): its most carried stories of the day, and its politics and money rows.
COUNTRY_DIR = 'country'
COUNTRY_TOP = 12
CC_RE = re.compile(r'^[A-Z]{2}$')
# Where an outlet is based comes from GDELT's own list of news sites by country (May 2018), trimmed to site and
# country code in outlet-countries.tsv. It is GDELT's estimate, from the places each site wrote about most; it is
# from 2018 and it can be wrong. A site that is not on the list has no country, and neither has a site on a shared
# host: the list knows where the host is, not who writes there.
OUTLET_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'outlet-countries.tsv')
SHARED_HOSTS = {
    'wordpress.com', 'blogspot.com', 'medium.com', 'substack.com', 'tumblr.com', 'typepad.com', 'weebly.com', 'wixsite.com',
    'github.io', 'google.com', 'facebook.com', 'youtube.com', 'yahoo.com', 'msn.com',
}
_outlets = None
# Files in the tiles folder that are not tiles. The Outer Index's two files belong here: without them the tile
# ageing below removed them on every run (they have no stories), so the index never kept a second day.
NOT_TILES = ('state.json', 'index.json', 'top.json', 'launches.json', 'money.json', 'politics.json', 'outer-index.json', 'outer-index-history.json')


def money_groups(themes):
    """V1Themes (THEME;THEME;...) to the sorted money groups, or [] when the story is not money news."""
    g = {MONEY[t] for t in themes.split(';') if t in MONEY}
    return sorted(g) if len(g) >= 2 and g & MONEY_CORE else []


def pol_group(theme):
    return POLITICS.get(theme) or ('party' if theme.startswith(POL_PARTY) else None)


def politics_groups(themes, marks):
    """V1Themes (THEME;THEME;...) and V2Themes (THEME,offset;THEME,offset;...) to the sorted politics groups, or []
    when the story is not politics news. The four rules are written out above POLITICS."""
    g = {pol_group(t) for t in themes.split(';')} - {None}
    if len(g & POL_CORE) < 2 or len(g) < 3:
        return []
    total = core = 0
    early = False
    for item in marks.split(';'):
        theme, _, offset = item.rpartition(',')
        if not theme or not offset.isdigit():
            continue
        total += 1
        if pol_group(theme) in POL_CORE:
            core += 1
            early = early or int(offset) < POL_EARLY
    return sorted(g) if early and core >= POL_SHARE * total else []


def title_key(t):
    """One headline, one key: lower case, the letters and digits of every script, the first 70 characters."""
    return re.sub(r'[\W_]+', ' ', t.lower()).strip()[:70] or t[:70]


def unmerge_once(out_dir, state):
    """Until 2026-11-11 the headline key kept Latin letters and digits only, so headlines in other scripts were
    merged with each other (every Arabic headline in a tile could become one "story" with a hundred outlets).
    Rows merged that way go back to their own outlet, once; state.json remembers it was done."""
    if state.get('unmerged'):
        return
    fixed = 0
    for name in os.listdir(out_dir):
        if not name.endswith('.json') or name in ('state.json', 'index.json', 'top.json', 'launches.json', 'outer-index.json', 'outer-index-history.json'):
            continue
        path = os.path.join(out_dir, name)
        try:
            with open(path, encoding='utf-8') as f:
                d = json.load(f)
            changed = 0
            for s in d.get('s', []):
                latin = re.sub(r'[^a-z0-9]+', ' ', s['t'].lower()).strip()
                if 'ds' in s and len(latin) * 2 < len(title_key(s['t'])):
                    for k in ('n', 'ds', 'us', 'dc'):
                        s.pop(k, None)
                    changed += 1
            if changed:
                with open(path, 'w', encoding='utf-8') as f:
                    json.dump(d, f, ensure_ascii=False, separators=(',', ':'))
                fixed += changed
        except Exception as e:  # noqa: BLE001
            print('unmerge skipped', name, e)
    state['unmerged'] = True
    print('rows unmerged (old headline key):', fixed)


def outlet_country(domain):
    """GDELT's country code for a news site, '' when it is not on the list. A subdomain takes its parent's."""
    global _outlets
    if _outlets is None:
        _outlets = {}
        try:
            with open(OUTLET_FILE, encoding='utf-8') as f:
                for line in f:
                    p = line.rstrip('\n').split('\t')
                    if len(p) == 2 and not line.startswith('#'):
                        _outlets[p[0]] = p[1]
        except OSError as e:
            print('no outlet list, so no outlet countries:', e)
    d = (domain or '').strip().lower()
    if d.startswith('www.'):
        d = d[4:]
    parts = d.split('.')
    for i in range(0, max(1, len(parts) - 1)):
        name = '.'.join(parts[i:])
        if name in SHARED_HOSTS:
            return ''
        if name in _outlets:
            return _outlets[name]
    return ''


def carry(first, s):
    """The same headline from another outlet: the first row lists it. n counts outlets, not copies."""
    names = first.setdefault('ds', [first['d']])
    urls = first.setdefault('us', [first['u']])
    urls += [''] * (len(names) - len(urls))  # a row from before links were kept: those outlets have no link
    if s['d'] in names:
        return
    first['n'] = first.get('n', 1) + 1
    if len(names) < OUTLETS:
        names.append(s['d'])
        urls.append(s['u'])


def finish(rows):
    """Before a file is written: each outlet's country (dc, left off when none is known), links in step with names."""
    for s in rows:
        names = s.get('ds') or [s['d']]
        if 'ds' in s:
            urls = s.get('us') or [s['u']]
            s['us'] = (urls + [''] * len(names))[:len(names)]
        codes = [outlet_country(d) for d in names]
        if any(codes):
            s['dc'] = codes
        else:
            s.pop('dc', None)
    return rows


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


def main_country(field):
    """The country a document names most often (V2Locations lists every mention). A tie goes to the one named
    first. Money news uses this, not the first city: a story about the Fed that opens in Seoul is American news."""
    count = {}
    for loc in field.split(';'):
        p = loc.split('#')
        if len(p) >= 7 and p[2]:
            count[p[2]] = count.get(p[2], 0) + 1  # dicts keep the order of first mention
    return max(count, key=count.get) if count else ''


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
                politics = politics_groups(cols[7], cols[8])
                if politics:
                    row['pg'] = politics
                # Every row carries the country it names most, so "news from a country" can leave out a story that
                # only opens there (country/<cc>.json). Money and politics news have needed it from the start.
                row['mc'] = main_country(cols[10]) or loc['cc']
                out.append(row)
    return out


def write_topic(out_dir, stories, cutoff, name, mark, per_country, total, covered=False):
    """A topic file (money.json, politics.json): the last 24 hours of one topic for the whole world, newest first,
    one row per headline with the outlets that carried it, at most per_country per country. `mark` is the row key
    that says a story belongs (mg, pg). With `covered`, half of a country's rows are the stories most outlets
    carry and half are its newest; without it they are all its newest. A row carried by several outlets lists them
    with each one's own link and country (ds, us, dc). Merges this run into the file there."""
    path = os.path.join(out_dir, name)
    old = []
    try:
        with open(path, encoding='utf-8') as f:
            old = json.load(f).get('s', [])
    except Exception:  # noqa: BLE001
        old = []
    fresh = [dict(s) for s in stories if s.get(mark)]  # copies: the tile rows keep their own outlet counts
    for s in fresh:
        for k in ('n', 'ds', 'us', 'dc'):
            s.pop(k, None)
    seen_url = set()
    by_title = {}
    merged = []
    for s in old + fresh:  # old first, so a headline keeps the count it already has
        if s['ts'] < cutoff or s['u'] in seen_url or 'mc' not in s:  # a row from before 'mc' existed is not kept
            continue
        seen_url.add(s['u'])
        key = title_key(s['t'])
        if key in by_title:
            carry(by_title[key], s)
            continue
        by_title[key] = s
        merged.append(s)
    newest = lambda s: s['ts']  # noqa: E731
    most = lambda s: (s.get('n', 1), s['ts'])  # noqa: E731
    by_country = {}
    for s in merged:
        by_country.setdefault(s.get('mc') or s['cc'], []).append(s)
    kept = []
    for rows in by_country.values():
        take = []
        if covered:
            take = sorted(rows, key=most, reverse=True)[:per_country // 2]
        have = {id(s) for s in take}
        for s in sorted(rows, key=newest, reverse=True):
            if len(take) >= per_country:
                break
            if id(s) not in have:
                take.append(s)
        kept += take
    if len(kept) > total:  # over the cap, the rows that go are the oldest (the least carried first, with covered)
        kept = sorted(kept, key=most if covered else newest, reverse=True)[:total]
    kept.sort(key=newest, reverse=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump({'updated': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'), 'source': 'GDELT', 's': finish(kept)}, f, ensure_ascii=False, separators=(',', ':'))
    return len(kept), len(by_country)


def write_money(out_dir, stories, cutoff):
    """money.json: newest first, at most MONEY_PER_COUNTRY per country."""
    return write_topic(out_dir, stories, cutoff, 'money.json', 'mg', MONEY_PER_COUNTRY, MONEY_MAX)


def write_politics(out_dir, stories, cutoff):
    """politics.json: for each country its most carried stories and its newest, at most POL_PER_COUNTRY."""
    return write_topic(out_dir, stories, cutoff, 'politics.json', 'pg', POL_PER_COUNTRY, POL_MAX, covered=True)


def at_home(s):
    """A story is a country's own when its first city is there and it names that country most (the app's test).
    A row from before every row carried 'mc' counts by its first city alone."""
    cc = s.get('cc') or ''
    return bool(CC_RE.match(cc)) and (s.get('mc') or cc) == cc


def write_countries(out_dir, cutoff):
    """country/<cc>.json for every country with news at home in the last day (cc is GDELT's FIPS code):
    'top' = its COUNTRY_TOP most carried stories from every tile (the newest first among equals), 'politics' and
    'money' = its rows of politics.json and money.json. One small file per country, so a country page reads a few
    kilobytes and not three whole-world files. country/index.json counts each country's stories by language, so
    the site map can list only the pages that have something to read. Files of countries that went quiet go."""
    def rows_of(name):
        try:
            with open(os.path.join(out_dir, name), encoding='utf-8') as f:
                return [s for s in json.load(f).get('s', []) if s.get('ts', '') >= cutoff and s.get('u') and s.get('t') and at_home(s)]
        except Exception:  # noqa: BLE001
            return []

    most = lambda s: (s.get('n', 1), s['ts'])  # noqa: E731
    best = {}
    for name in os.listdir(out_dir):
        if not name.endswith('.json') or name in NOT_TILES:
            continue
        for s in rows_of(name):
            mine = best.setdefault(s['cc'], {})
            key = title_key(s['t'])[:60]
            if key not in mine or most(s) > most(mine[key]):
                mine[key] = s
    topics = {}
    for part, name in (('politics', 'politics.json'), ('money', 'money.json')):
        for s in rows_of(name):
            topics.setdefault(s['cc'], {}).setdefault(part, []).append(s)

    folder = os.path.join(out_dir, COUNTRY_DIR)
    os.makedirs(folder, exist_ok=True)
    now = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    counts = {}
    for cc in sorted(set(best) | set(topics)):
        top = sorted(best.get(cc, {}).values(), key=most, reverse=True)[:COUNTRY_TOP]
        politics = topics.get(cc, {}).get('politics', [])
        money = topics.get(cc, {}).get('money', [])
        by_lang = {}
        seen = set()
        for s in top + politics + money:
            if s['u'] not in seen:
                seen.add(s['u'])
                by_lang[s.get('lg') or 'und'] = by_lang.get(s.get('lg') or 'und', 0) + 1
        counts[cc] = by_lang
        with open(os.path.join(folder, f'{cc}.json'), 'w', encoding='utf-8') as f:
            json.dump({'updated': now, 'source': 'GDELT', 'cc': cc, 'top': finish(top), 'politics': politics, 'money': money}, f, ensure_ascii=False, separators=(',', ':'))
    for name in os.listdir(folder):
        if name.endswith('.json') and name != 'index.json' and name[:-5] not in counts:
            os.remove(os.path.join(folder, name))
    with open(os.path.join(folder, 'index.json'), 'w', encoding='utf-8') as f:
        json.dump({'updated': now, 'source': 'GDELT', 'c': counts}, f, separators=(',', ':'))
    return len(counts), sum(sum(c.values()) for c in counts.values())


def main(out_dir):
    os.makedirs(out_dir, exist_ok=True)
    state = load_state(out_dir)
    unmerge_once(out_dir, state)
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
        for s in old + fresh:  # old first, so a headline keeps the outlets it already has
            if s['ts'] < cutoff or s['u'] in seen_url:
                continue
            seen_url.add(s['u'])
            key = title_key(s['t'])
            if key in by_title:
                carry(by_title[key], s)
                continue
            by_title[key] = s
            merged.append(s)
        merged.sort(key=lambda s: (s.get('n', 1) > 1, s['ts']), reverse=True)
        merged = merged[:MAX_PER_TILE]
        with open(path, 'w', encoding='utf-8') as f:
            json.dump({'tile': tile, 'updated': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'), 'source': 'GDELT', 's': finish(merged)}, f, ensure_ascii=False, separators=(',', ':'))
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
        key = title_key(s['t'])[:60]
        if key in seen_titles:
            continue
        seen_titles.add(key)
        ranked.append(s)
        if len(ranked) >= 60:
            break
    with open(os.path.join(out_dir, 'top.json'), 'w', encoding='utf-8') as f:
        json.dump({'updated': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'), 'source': 'GDELT', 's': finish(ranked)}, f, ensure_ascii=False, separators=(',', ':'))

    with open(os.path.join(out_dir, 'index.json'), 'w', encoding='utf-8') as f:
        tiles = sorted(n[:-5] for n in os.listdir(out_dir) if n.endswith('.json') and n not in NOT_TILES)
        json.dump({'updated': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'), 'tiles': tiles, 'source': 'GDELT Project', 'license': 'cite GDELT; headline and link only'}, f)
    print('tiles written:', written, '| top stories:', len(ranked))
    try:
        rows, countries = write_money(out_dir, stories, cutoff)
        print('money stories:', rows, '| countries:', countries)
    except Exception as e:  # noqa: BLE001  (money news is extra: the tiles above are already written)
        print('money.json not written:', e)
    try:
        rows, countries = write_politics(out_dir, stories, cutoff)
        print('politics stories:', rows, '| countries:', countries)
    except Exception as e:  # noqa: BLE001  (politics news is extra too)
        print('politics.json not written:', e)
    try:
        countries, rows = write_countries(out_dir, cutoff)
        print('country files:', countries, '| their stories:', rows)
    except Exception as e:  # noqa: BLE001  (country files are extra too)
        print('country files not written:', e)


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else 'tiles')
