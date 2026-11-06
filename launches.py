#!/usr/bin/env python3
"""Upcoming rocket launches from Launch Library 2 (The Space Devs), written to <out>/launches.json.

The API allows about 15 calls an hour per address and Cloudflare's shared addresses hit that at once, so the job
fetches it from here instead, at most once an hour (the file's own timestamp decides), and the site reads the file.
Data: The Space Devs, https://thespacedevs.com. Usage: python3 -I launches.py out/tiles
"""
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone

URL = 'https://ll.thespacedevs.com/2.2.0/launch/upcoming/?limit=40&mode=normal&hide_recent_previous=true'
MIN_AGE_MIN = 55


def main(out_dir: str) -> int:
    path = os.path.join(out_dir, 'launches.json')
    now = datetime.now(timezone.utc)
    try:
        with open(path, encoding='utf-8') as f:
            old = json.load(f)
        age = (now - datetime.strptime(old['updated'], '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc)).total_seconds() / 60
        if age < MIN_AGE_MIN and old.get('launches'):
            print(f'launches: kept ({age:.0f} min old, {len(old["launches"])} launches)')
            return 0
    except Exception:
        pass
    req = urllib.request.Request(URL, headers={'User-Agent': 'OuterView news job (https://outerview.world)'})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.load(r)
    except Exception as e:  # keep the old file; the site keeps working
        print(f'launches: fetch failed ({e}); kept the old file')
        return 0
    launches = []
    for l in data.get('results', []):
        pad = l.get('pad') or {}
        loc = pad.get('location') or {}
        try:
            lat, lng = float(pad.get('latitude')), float(pad.get('longitude'))
        except (TypeError, ValueError):
            continue
        launches.append({
            'id': l.get('id'),
            'slug': l.get('slug'),
            'name': l.get('name'),
            'net': l.get('net'),
            'window_start': l.get('window_start'),
            'status': (l.get('status') or {}).get('abbrev'),
            'provider': (l.get('launch_service_provider') or {}).get('name'),
            'pad': pad.get('name'),
            'location': loc.get('name'),
            'timezone': loc.get('timezone_name'),
            'lat': lat,
            'lng': lng,
            'mission': ((l.get('mission') or {}).get('description') or '')[:400],
            'image': l.get('image') if isinstance(l.get('image'), str) else ((l.get('image') or {}).get('image_url') if isinstance(l.get('image'), dict) else None),
            'video': ((l.get('vidURLs') or [{}])[0]).get('url') if l.get('vidURLs') else None,
        })
    with open(path, 'w', encoding='utf-8') as f:
        json.dump({'updated': now.strftime('%Y-%m-%dT%H:%M:%SZ'), 'source': 'Launch Library 2 (The Space Devs)', 'launches': launches}, f, ensure_ascii=False, separators=(',', ':'))
    print(f'launches: {len(launches)} written')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else 'out/tiles'))
