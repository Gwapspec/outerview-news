#!/usr/bin/env python3
"""The wind picture for OuterView's Wind layer (world-view docs/WIND.md, Game Plan row 9a).

Every news run calls this; it works only when NOAA has a GFS run newer than the one already published: it fetches
that run's 10 m wind (UGRD, VGRD) analysis (f000) on the 1-degree grid from the NOMADS GRIB filter (about 156 KB),
decodes it with ECMWF's ecCodes (installed on demand, Apache 2.0) and writes

  <out>/latest.png  360 x 181: red = wind toward the east (u), green = toward the north (v), 0..255 for -50..50 m/s;
                    rows from 90 N down to 90 S, columns from 0 E eastward
  <out>/meta.json   the run, the grid and the scale

NOAA's data is public domain. One line of output; nothing new is not an error.
    python3 -I wind.py out/wind
"""
import datetime as dt
import json
import os
import struct
import subprocess
import sys
import urllib.request
import zlib

OUT = sys.argv[1] if len(sys.argv) > 1 else 'out/wind'
FILTER = ('https://nomads.ncep.noaa.gov/cgi-bin/filter_gfs_1p00.pl?file=gfs.t{c}z.pgrb2.1p00.f000'
          '&lev_10_m_above_ground=on&var_UGRD=on&var_VGRD=on&dir=%2Fgfs.{d}%2F{c}%2Fatmos')
UA = {'User-Agent': 'OuterView (https://outerview.world) wind'}
LO, HI = -50.0, 50.0
W, H = 360, 181
LIB = '/tmp/windlib'


def runs(now):
    """The GFS runs to try, newest first: one starts every 6 hours and is on NOMADS about 3.5 hours later."""
    t = now - dt.timedelta(hours=3, minutes=30)
    t = t.replace(hour=t.hour - t.hour % 6, minute=0, second=0, microsecond=0)
    return [t - dt.timedelta(hours=6 * k) for k in range(4)]


def png(rows):
    """An 8-bit RGB PNG from rows of bytes (no library: the format is a few chunks)."""
    raw = b''.join(b'\x00' + r for r in rows)

    def chunk(tag, data):
        return struct.pack('>I', len(data)) + tag + data + struct.pack('>I', zlib.crc32(tag + data) & 0xffffffff)

    return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', W, H, 8, 2, 0, 0, 0)) + chunk(b'IDAT', zlib.compress(raw, 9)) + chunk(b'IEND', b'')


def ecc():
    try:
        import eccodes  # noqa: F401
    except ImportError:
        cmd = [sys.executable, '-m', 'pip', 'install', '-q', '--disable-pip-version-check', '--target', LIB, 'eccodes==2.43.0']
        # Ubuntu's own Python marks itself "externally managed"; installing into a folder of our own is safe.
        if subprocess.run(cmd).returncode != 0:
            subprocess.run(cmd + ['--break-system-packages'], check=True)
        sys.path.insert(0, LIB)
    import eccodes
    return eccodes


def decode(grib):
    """The u and v grids (rows from 90 N, columns from 0 E) from the filter's two messages."""
    ec = ecc()
    path = '/tmp/gfs-wind.grib2'
    open(path, 'wb').write(grib)
    out = {}
    with open(path, 'rb') as f:
        while True:
            g = ec.codes_grib_new_from_file(f)
            if g is None:
                break
            try:
                grid = (ec.codes_get(g, 'Ni'), ec.codes_get(g, 'Nj'), ec.codes_get(g, 'latitudeOfFirstGridPointInDegrees'), ec.codes_get(g, 'longitudeOfFirstGridPointInDegrees'), ec.codes_get(g, 'iDirectionIncrementInDegrees'))
                if grid != (W, H, 90, 0, 1):
                    raise ValueError(f'unexpected grid {grid}')
                out[ec.codes_get(g, 'shortName')] = ec.codes_get_values(g).reshape(H, W)
            finally:
                ec.codes_release(g)
    return out['10u'], out['10v']


def main():
    os.makedirs(OUT, exist_ok=True)
    meta_path = os.path.join(OUT, 'meta.json')
    try:
        have = json.load(open(meta_path)).get('run')
    except Exception:
        have = None
    now = dt.datetime.now(dt.timezone.utc)
    for run in runs(now):
        stamp = run.strftime('%Y-%m-%dT%H:00Z')
        if have and stamp <= have:
            print(f'wind: {have} is the newest published')
            return
        url = FILTER.format(c=run.strftime('%H'), d=run.strftime('%Y%m%d'))
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
                grib = r.read()
        except Exception:
            continue  # not on NOMADS yet, or a blip: the run before
        if grib[:4] != b'GRIB':
            continue
        u, v = decode(grib)
        import numpy as np
        q = lambda a: np.clip(np.rint((a - LO) / (HI - LO) * 255), 0, 255).astype(np.uint8)
        rgb = np.dstack([q(u), q(v), np.zeros((H, W), np.uint8)])
        open(os.path.join(OUT, 'latest.png'), 'wb').write(png([rgb[j].tobytes() for j in range(H)]))
        meta = {'run': stamp, 'valid': stamp, 'model': 'NOAA GFS, 1 degree, 10 m wind, analysis (f000)', 'w': W, 'h': H, 'lat0': 90, 'lon0': 0, 'step': 1, 'min': LO, 'max': HI, 'made': now.strftime('%Y-%m-%dT%H:%MZ'), 'source': 'NOAA NOMADS (public domain)'}
        json.dump(meta, open(meta_path, 'w'), separators=(',', ':'))
        print(f'wind: {stamp} written, {os.path.getsize(os.path.join(OUT, "latest.png")) // 1024} KB, fastest {float(np.hypot(u, v).max()):.1f} m/s')
        return
    print(f'wind: no newer GFS run reachable; kept {have}')


if __name__ == '__main__':
    main()
