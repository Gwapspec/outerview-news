"""Opening hours for OuterView's places (world-view docs/HOURS.md, Game Plan row 25, module 1).

Once a week: OpenStreetMap's places with `opening_hours` (OpenStreetMap US's Layercake `pois.parquet`, read with DuckDB,
only the columns needed) are matched to each city's places on OuterView's Boards (Overture ids), by name within 80 m,
and each match's hours are worked out for the next 14 days in the place's own time zone, with its country's public
holidays (the `opening-hours` crate's Python build, MIT or Apache-2.0). The output is plain minutes, so the app needs no
parser, and hours older than two weeks are never shown.

Writes out/<cc>_<name>.json per city and out/index.json; the workflow publishes them on the `hours` branch, rewritten
each run. This script is the method of matching that ODbL 4.6 asks us to offer; the files are the OSM-derived table.
Data: (c) OpenStreetMap contributors, ODbL 1.0. Places: Overture Maps (see places/README.md).

    python3 -I places/hours.py                  # every city (the full extract, about 10 minutes of reading)
    python3 -I places/hours.py fr/paris de/berlin  # a few cities, read box by box from the file
"""
import datetime as dt
import json
import math
import os
import re
import sys
import time
import unicodedata
import urllib.request

import duckdb
from zoneinfo import ZoneInfo
import opening_hours as oh

LAYERCAKE = 'https://data.openstreetmap.us/layercake/pois.parquet'
SITE = 'https://outerview.world'
UA = 'OuterView hours job (https://outerview.world; https://github.com/Gwapspec/outerview-news)'
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.environ.get('HOURS_OUT', os.path.join(HERE, '..', 'out-hours'))
DAYS = 14
NEAR_M = 80
MARGIN = 0.002  # degrees around a city's places when reading OpenStreetMap


def fold(s):
    """A name as compared: no accents, lower case, letters and digits only."""
    s = unicodedata.normalize('NFKD', str(s or '')).lower()
    s = ''.join(c for c in s if not unicodedata.combining(c))
    return re.sub(r'[^\w]+', ' ', s, flags=re.UNICODE).replace('_', ' ').strip()


def same_name(a, b):
    """Two folded names are the same place's: equal, or one is the other with a word or two more ("Zara" is not
    "Zara Home": the shorter must be at least two thirds of the longer, and 4 letters or more)."""
    if not a or not b:
        return False
    if a == b:
        return True
    short, long_ = (a, b) if len(a) <= len(b) else (b, a)
    return len(short) >= 4 and len(short) >= 0.66 * len(long_) and (long_.startswith(short + ' ') or long_.endswith(' ' + short) or f' {short} ' in f' {long_} ')


def metres(la1, lo1, la2, lo2):
    r = math.radians
    h = math.sin(r(la2 - la1) / 2) ** 2 + math.cos(r(la1)) * math.cos(r(la2)) * math.sin(r(lo2 - lo1) / 2) ** 2
    return 2 * 6371000 * math.asin(math.sqrt(h))


def get_json(url):
    req = urllib.request.Request(url, headers={'user-agent': UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def our_places(city_id):
    """A city's places on the Boards: the seed file when the job made it, else the site's answer (the first cities were
    seeded by hand and live only in the site's database). Every shelf holds 60 at most."""
    path = os.path.join(HERE, 'data', city_id.replace('/', '_') + '.jsonl')
    if os.path.exists(path):
        with open(path, encoding='utf-8') as f:
            return [json.loads(line) for line in f if line.strip()]
    try:
        return get_json(f'{SITE}/api/pois?place={city_id}&n=60').get('items') or []
    except Exception as e:  # noqa: BLE001 - one city's miss is not the run's
        print(f'  {city_id}: the site did not answer ({e})', flush=True)
        return []


def osm_rows(con, table, box):
    xmin, ymin, xmax, ymax = box
    return con.execute(
        f"""SELECT type, id, name, names, opening_hours, wikidata, (bbox.xmin + bbox.xmax) / 2 AS lng, (bbox.ymin + bbox.ymax) / 2 AS lat
            FROM {table} WHERE bbox.xmin BETWEEN ? AND ? AND bbox.ymin BETWEEN ? AND ?""",
        [xmin, xmax, ymin, ymax],
    ).fetchall()


def names_of(row):
    _, _, name, names, *_ = row
    out = {fold(n) for n in (name or [])}
    for vals in (names or {}).values():
        out.update(fold(n) for n in (vals or []))
    out.discard('')
    return out


def match(places, candidates):
    """Each of our places to at most one OpenStreetMap object (the nearest with the same name within 80 m), and each
    object to at most one of our places (the nearest)."""
    cells = {}
    for c in candidates:
        cells.setdefault((round(c[7], 3), round(c[6], 3)), []).append(c)
    best = {}  # osm key -> (metres, place, row)
    for p in places:
        n = fold(p.get('name'))
        if not n:
            continue
        la, lo = p['lat'], p['lng']
        found = None
        for dla in (-0.001, 0, 0.001):
            for dlo in (-0.001, 0, 0.001):
                for c in cells.get((round(la + dla, 3), round(lo + dlo, 3)), []):
                    m = metres(la, lo, c[7], c[6])
                    if m <= NEAR_M and any(same_name(n, x) for x in names_of(c)) and (found is None or m < found[0]):
                        found = (m, c)
        if found:
            key = f'{found[1][0][0]}{found[1][1]}'
            if key not in best or found[0] < best[key][0]:
                best[key] = (found[0], p, found[1])
    return [(p, c) for _, p, c in best.values()]


def window(value, lat, lng, now):
    """The next 14 days of a place's hours: (its local date today, [open start, end, ...] in minutes from that date's
    midnight on the place's own clock, a comment or ''), or None when OpenStreetMap's value cannot be read. The parser
    finds the time zone and the country's holidays from the coordinates."""
    try:
        h = oh.OpeningHours(value, coords=(lat, lng))
        first = next(h.intervals(now), None)
        if first is None:
            return None
        tz = first[0].tzinfo
        d0 = first[0].date()
        start = dt.datetime.combine(d0, dt.time(0, 0), tzinfo=tz)
        end = start + dt.timedelta(days=DAYS)
        flat, note = [], ''
        for a, b, state, comment in h.intervals(start, end):
            b = end if b is None or b > end else b
            s = (a.date() - d0).days * 1440 + a.hour * 60 + a.minute
            e = (b.date() - d0).days * 1440 + b.hour * 60 + b.minute
            if state == oh.State.OPEN and e > s:
                if flat and flat[-1] == s:
                    flat[-1] = e  # one stretch, not two touching ones
                else:
                    flat += [s, e]
            elif state == oh.State.CLOSED and comment and not note:
                note = comment.strip()[:100]
        return d0.isoformat(), flat, note
    except Exception:  # noqa: BLE001 - a value the parser cannot read is left out
        return None


def main(args):
    os.makedirs(OUT, exist_ok=True)
    # Every city on the site (the first ones were seeded by hand and are not in the seed queue): id, name, cc, lat, lng.
    every = json.load(open(os.path.join(HERE, '..', 'cities.json'), encoding='utf-8'))['cities']
    cities = [{'id': c[0]} for c in every if not args or c[0] in args]
    con = duckdb.connect()
    con.execute('INSTALL httpfs; LOAD httpfs;')
    t0 = time.time()
    if len(cities) > 20:
        # The full extract: every named place with hours, once (only five columns are read).
        con.execute(
            f"""CREATE TABLE osm AS SELECT type, id, name, names, opening_hours, wikidata, bbox FROM read_parquet('{LAYERCAKE}')
                WHERE opening_hours IS NOT NULL AND name IS NOT NULL"""
        )
        table = 'osm'
        print(f'extract: {con.execute("SELECT count(*) FROM osm").fetchone()[0]} places with hours, {time.time() - t0:.0f} s', flush=True)
    else:
        table = f"(SELECT * FROM read_parquet('{LAYERCAKE}') WHERE opening_hours IS NOT NULL AND name IS NOT NULL)"
    today = dt.datetime.now(ZoneInfo('UTC'))
    index, total, unread = {}, 0, 0
    for i, city in enumerate(cities):
        places = our_places(city['id'])
        if not places:
            continue
        lats = [p['lat'] for p in places]
        lngs = [p['lng'] for p in places]
        box = (min(lngs) - MARGIN, min(lats) - MARGIN, max(lngs) + MARGIN, max(lats) + MARGIN)
        rows = []
        for p, c in match(places, osm_rows(con, table, box)):
            w = window(c[4], c[7], c[6], today)
            if w is None:
                unread += 1
                continue
            d0, flat, note = w
            row = {'id': p['id'], 'osm': f'{c[0][0]}{c[1]}', 'd': d0, 'o': flat}
            if note:
                row['n'] = note
            if c[5]:
                row['wd'] = c[5]  # module 2's photos
            rows.append(row)
        if rows:
            name = city['id'].replace('/', '_')
            with open(os.path.join(OUT, f'{name}.json'), 'w', encoding='utf-8') as f:
                json.dump({'place': city['id'], 'made': today.strftime('%Y-%m-%d'), 'rows': rows}, f, ensure_ascii=False, separators=(',', ':'))
            index[city['id']] = {'n': len(rows), 'of': len(places), 'made': today.strftime('%Y-%m-%d')}
            total += len(rows)
        if (i + 1) % 200 == 0 or len(cities) <= 20:
            print(f'{i + 1}/{len(cities)} {city["id"]}: {len(rows)} of {len(places)} with hours ({time.time() - t0:.0f} s)', flush=True)
        if not os.path.exists(os.path.join(HERE, 'data', city['id'].replace('/', '_') + '.jsonl')):
            time.sleep(0.3)  # the site's answer: gently
    with open(os.path.join(OUT, 'index.json'), 'w', encoding='utf-8') as f:
        json.dump(index, f, separators=(',', ':'))
    print(f'done: {total} places with hours in {len(index)} cities; {unread} values the parser could not read; {time.time() - t0:.0f} s', flush=True)


if __name__ == '__main__':
    main(sys.argv[1:])
