#!/usr/bin/env python3
"""The Outer Index: one number per city for how much is happening there today.

Usage: python3 -I index.py <tiles_dir> <cities.json>

Reads every story tile written by gkg.py, keeps the stories of the last 24 hours, assigns each one to the nearest
city of 150,000 people or more within 60 km, and writes <tiles_dir>/outer-index.json: every city with at least one story,
ranked. The score is 0 to 100 on a log scale against the loudest city of the day, so it reads the same way every
day: 100 is the loudest place on Earth right now, 50 is a city with roughly the square root of that attention.
Weight = stories + half the extra outlets (a story carried by 8 outlets counts more than one carried by 1). A story
whose place name does not mention the city counts 0.6 (GDELT sometimes places a story at a country's centroid,
and the nearest mid-size city would otherwise take the credit). outer-index-history.json keeps each city's score
for the last 14 days, so a page can say "up 12 since yesterday".
No AI, no opinion: counts of placed headlines from the GDELT Project, nothing else.
"""
import glob
import json
import math
import os
import sys
from datetime import datetime, timedelta, timezone

RADIUS_KM = 60
HOURS = 24


def km(a_lat, a_lng, b_lat, b_lng):
    r = math.pi / 180
    h = math.sin((b_lat - a_lat) * r / 2) ** 2 + math.cos(a_lat * r) * math.cos(b_lat * r) * math.sin((b_lng - a_lng) * r / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(h))


def main(tiles_dir, cities_path):
    with open(cities_path) as f:
        cities = json.load(f)['cities']  # [id, name, cc, lat, lng, pop]
    cells = {}
    for c in cities:
        cells.setdefault((int(math.floor(c[3])), int(math.floor(c[4]))), []).append(c)

    def nearest(lat, lng):
        best, best_d = None, RADIUS_KM
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                for c in cells.get((int(math.floor(lat)) + dy, int(math.floor(lng)) + dx), []):
                    d = km(lat, lng, c[3], c[4])
                    if d < best_d:
                        best, best_d = c, d
        return best

    cutoff = (datetime.now(timezone.utc) - timedelta(hours=HOURS)).strftime('%Y%m%d%H%M%S')
    acc = {}
    seen = 0
    for path in glob.glob(os.path.join(tiles_dir, '*.json')):
        name = os.path.basename(path)
        if name in ('index.json', 'outer-index.json', 'launches.json', 'top.json', 'state.json', 'money.json'):
            continue
        try:
            with open(path) as f:
                stories = json.load(f).get('s', [])
        except Exception:
            continue
        for s in stories:
            try:
                if str(s.get('ts', '')) < cutoff:
                    continue
                lat, lng = float(s['la']), float(s['lo'])
            except Exception:
                continue
            c = nearest(lat, lng)
            if not c:
                continue
            seen += 1
            n = int(s.get('n') or 1)
            a = acc.setdefault(c[0], {'id': c[0], 'name': c[1], 'cc': c[2], 'lat': c[3], 'lng': c[4], 'stories': 0, 'outlets': 0, 'top': None})
            pl = str(s.get('pl', '')).lower()
            cname = c[1].lower()
            match = 1.0 if (cname in pl or pl.split(',')[0].strip() in cname) else 0.6
            a['stories'] += 1
            a['outlets'] += n
            a['w'] = a.get('w', 0.0) + match * (1 + 0.5 * max(0, n - 1))
            top = a['top']
            if top is None or n > top['n'] or (n == top['n'] and str(s.get('ts', '')) > top['ts']):
                a['top'] = {'t': str(s.get('t', ''))[:120], 'u': s.get('u', ''), 'd': s.get('d', ''), 'n': n, 'ts': str(s.get('ts', ''))}

    rows = list(acc.values())
    max_w = max([a['w'] for a in rows] + [1.0])
    for a in rows:
        a['score'] = int(round(100 * math.log1p(a['w']) / math.log1p(max_w)))
        del a['w']
    rows.sort(key=lambda a: (-a['score'], -a['stories'], a['name']))
    for i, a in enumerate(rows):
        a['rank'] = i + 1

    # History: today's score per city, kept 14 days, and yesterday's delta on each row.
    hist_path = os.path.join(tiles_dir, 'outer-index-history.json')
    try:
        with open(hist_path) as f:
            hist = json.load(f)
    except Exception:
        hist = {'days': {}}
    today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    hist['days'][today] = {a['id']: a['score'] for a in rows}
    keep = sorted(hist['days'].keys())[-14:]
    hist['days'] = {d: hist['days'][d] for d in keep}
    prev_days = [d for d in keep if d < today]
    prev = hist['days'][prev_days[-1]] if prev_days else {}
    for a in rows:
        a['delta'] = (a['score'] - prev[a['id']]) if a['id'] in prev else None
    with open(hist_path, 'w') as f:
        json.dump(hist, f, separators=(',', ':'))
    out = {
        'updated': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
        'hours': HOURS,
        'radiusKm': RADIUS_KM,
        'placed': seen,
        'cities': rows,
    }
    with open(os.path.join(tiles_dir, 'outer-index.json'), 'w') as f:
        json.dump(out, f, separators=(',', ':'), ensure_ascii=False)
    print(f'index: {len(rows)} cities, {seen} stories placed, loudest {rows[0]["name"] if rows else "none"}')


if __name__ == '__main__':
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)
    main(sys.argv[1], sys.argv[2])
