"""Stock exchanges' trading sessions for OuterView's "Markets now" (world-view docs/MARKETS.md, Game Plan row 72).

Once a week, beside the opening hours: each exchange's next 14 days from `exchange_calendars` (Apache-2.0), in the
exchange's own time and in the hours' form (start and end minutes from the first local day's midnight; a lunch break is
two stretches; early closes and late opens as the calendar has them). A weekday with no session is a holiday (`hol`, the
days from the start). `w` is how many of the 14 days the calendar knows: a calendar built from announced lists (China,
India, Singapore) can end before the window does, and the app then shows nothing for those days rather than a guess.
Only facts of time: no prices, no index levels (no free source allows showing them; docs/MARKETS.md).

    python3 -I places/markets.py        # writes $HOURS_OUT/markets.json
"""
import datetime as dt
import json
import os
import time

import exchange_calendars as xc
import pandas as pd

OUT = os.environ.get('HOURS_OUT', os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'out-hours'))
DAYS = 14

# MIC: (name, city, ISO country, lat, lng, the exchange's own site for prices). One exchange a country (its main one);
# `world` lists the twelve on "Markets now", west to east.
EXCHANGES = {
    'XNYS': ('NYSE', 'New York', 'US', 40.7069, -74.0113, 'https://www.nyse.com'),
    'XTSE': ('TSX', 'Toronto', 'CA', 43.6487, -79.3817, 'https://www.tsx.com'),
    'XMEX': ('BMV', 'Mexico City', 'MX', 19.4271, -99.1677, 'https://www.bmv.com.mx'),
    'BVMF': ('B3', 'São Paulo', 'BR', -23.5475, -46.6361, 'https://www.b3.com.br'),
    'XBUE': ('BYMA', 'Buenos Aires', 'AR', -34.6037, -58.3816, 'https://www.byma.com.ar'),
    'XSGO': ('Santiago Exchange', 'Santiago', 'CL', -33.4489, -70.6693, 'https://www.bolsadesantiago.com'),
    'XBOG': ('BVC', 'Bogotá', 'CO', 4.711, -74.0721, 'https://www.bvc.com.co'),
    'XLIM': ('BVL', 'Lima', 'PE', -12.0464, -77.0428, 'https://www.bvl.com.pe'),
    'XLON': ('LSE', 'London', 'GB', 51.5155, -0.099, 'https://www.londonstockexchange.com'),
    'XDUB': ('Euronext Dublin', 'Dublin', 'IE', 53.3498, -6.2603, 'https://live.euronext.com'),
    'XLIS': ('Euronext Lisbon', 'Lisbon', 'PT', 38.7223, -9.1393, 'https://live.euronext.com'),
    'XMAD': ('BME', 'Madrid', 'ES', 40.4168, -3.7038, 'https://www.bolsasymercados.es'),
    'XPAR': ('Euronext Paris', 'Paris', 'FR', 48.8566, 2.3522, 'https://live.euronext.com'),
    'XBRU': ('Euronext Brussels', 'Brussels', 'BE', 50.8503, 4.3517, 'https://live.euronext.com'),
    'XAMS': ('Euronext Amsterdam', 'Amsterdam', 'NL', 52.3676, 4.9041, 'https://live.euronext.com'),
    'XLUX': ('Luxembourg Stock Exchange', 'Luxembourg', 'LU', 49.6116, 6.1319, 'https://www.luxse.com'),
    'XETR': ('Xetra', 'Frankfurt', 'DE', 50.1155, 8.6842, 'https://www.boerse-frankfurt.de'),
    'XSWX': ('SIX', 'Zurich', 'CH', 47.3769, 8.5417, 'https://www.six-group.com'),
    'XMIL': ('Borsa Italiana', 'Milan', 'IT', 45.4642, 9.19, 'https://www.borsaitaliana.it'),
    'XWBO': ('Wiener Börse', 'Vienna', 'AT', 48.2082, 16.3738, 'https://www.wienerborse.at'),
    'XLJU': ('Ljubljana Stock Exchange', 'Ljubljana', 'SI', 46.0569, 14.5058, 'https://ljse.si'),
    'XZAG': ('Zagreb Stock Exchange', 'Zagreb', 'HR', 45.815, 15.9819, 'https://zse.hr'),
    'XPRA': ('Prague Stock Exchange', 'Prague', 'CZ', 50.0755, 14.4378, 'https://www.pse.cz'),
    'XBUD': ('Budapest Stock Exchange', 'Budapest', 'HU', 47.4979, 19.0402, 'https://www.bse.hu'),
    'XWAR': ('GPW', 'Warsaw', 'PL', 52.2297, 21.0122, 'https://www.gpw.pl'),
    'XCSE': ('Nasdaq Copenhagen', 'Copenhagen', 'DK', 55.6761, 12.5683, 'https://www.nasdaqomxnordic.com'),
    'XOSL': ('Oslo Børs', 'Oslo', 'NO', 59.9139, 10.7522, 'https://live.euronext.com'),
    'XSTO': ('Nasdaq Stockholm', 'Stockholm', 'SE', 59.3293, 18.0686, 'https://www.nasdaqomxnordic.com'),
    'XHEL': ('Nasdaq Helsinki', 'Helsinki', 'FI', 60.1699, 24.9384, 'https://www.nasdaqomxnordic.com'),
    'XICE': ('Nasdaq Iceland', 'Reykjavík', 'IS', 64.1466, -21.9426, 'https://www.nasdaqomxnordic.com'),
    'XTAL': ('Nasdaq Tallinn', 'Tallinn', 'EE', 59.437, 24.7536, 'https://nasdaqbaltic.com'),
    'XRIS': ('Nasdaq Riga', 'Riga', 'LV', 56.9496, 24.1052, 'https://nasdaqbaltic.com'),
    'XLIT': ('Nasdaq Vilnius', 'Vilnius', 'LT', 54.6872, 25.2797, 'https://nasdaqbaltic.com'),
    'XBSE': ('Bucharest Stock Exchange', 'Bucharest', 'RO', 44.4268, 26.1025, 'https://bvb.ro'),
    'ASEX': ('Athens Exchange', 'Athens', 'GR', 37.9838, 23.7275, 'https://www.athexgroup.gr'),
    'XCYS': ('Cyprus Stock Exchange', 'Nicosia', 'CY', 35.1856, 33.3823, 'https://www.cse.com.cy'),
    'XIST': ('Borsa Istanbul', 'Istanbul', 'TR', 41.0082, 28.9784, 'https://www.borsaistanbul.com'),
    'XMOS': ('Moscow Exchange', 'Moscow', 'RU', 55.7558, 37.6173, 'https://www.moex.com'),
    'XTAE': ('TASE', 'Tel Aviv', 'IL', 32.0853, 34.7818, 'https://www.tase.co.il'),
    'XSAU': ('Saudi Exchange', 'Riyadh', 'SA', 24.7136, 46.6753, 'https://www.saudiexchange.sa'),
    'XDFM': ('Dubai Financial Market', 'Dubai', 'AE', 25.2048, 55.2708, 'https://www.dfm.ae'),
    'XJSE': ('JSE', 'Johannesburg', 'ZA', -26.2041, 28.0473, 'https://www.jse.co.za'),
    'XKAR': ('PSX', 'Karachi', 'PK', 24.8607, 67.0011, 'https://www.psx.com.pk'),
    'XBOM': ('BSE', 'Mumbai', 'IN', 19.076, 72.8777, 'https://www.bseindia.com'),
    'XSHG': ('SSE', 'Shanghai', 'CN', 31.2304, 121.4737, 'https://english.sse.com.cn'),
    'XHKG': ('HKEX', 'Hong Kong', 'HK', 22.2783, 114.1747, 'https://www.hkex.com.hk'),
    'XTAI': ('TWSE', 'Taipei', 'TW', 25.033, 121.5654, 'https://www.twse.com.tw/en'),
    'XKRX': ('KRX', 'Seoul', 'KR', 37.5665, 126.978, 'https://global.krx.co.kr'),
    'XTKS': ('JPX', 'Tokyo', 'JP', 35.6762, 139.6503, 'https://www.jpx.co.jp/english'),
    'XBKK': ('SET', 'Bangkok', 'TH', 13.7563, 100.5018, 'https://www.set.or.th'),
    'XKLS': ('Bursa Malaysia', 'Kuala Lumpur', 'MY', 3.139, 101.6869, 'https://www.bursamalaysia.com'),
    'XSES': ('SGX', 'Singapore', 'SG', 1.3521, 103.8198, 'https://www.sgx.com'),
    'XIDX': ('IDX', 'Jakarta', 'ID', -6.2088, 106.8456, 'https://www.idx.co.id'),
    'XPHS': ('PSE', 'Manila', 'PH', 14.5547, 121.0244, 'https://www.pse.com.ph'),
    'XASX': ('ASX', 'Sydney', 'AU', -33.8688, 151.2093, 'https://www.asx.com.au'),
    'XNZE': ('NZX', 'Wellington', 'NZ', -41.2865, 174.7762, 'https://www.nzx.com'),
}
WORLD = ['XNYS', 'XTSE', 'BVMF', 'XLON', 'XETR', 'XPAR', 'XJSE', 'XBOM', 'XSHG', 'XHKG', 'XTKS', 'XASX']


def minutes(ts, d0, tz):
    t = ts.tz_convert(tz)
    return (t.date() - d0).days * 1440 + t.hour * 60 + t.minute


def sessions(mic, now):
    """One exchange's next 14 days on its own clock, or None when its calendar cannot say."""
    c = xc.get_calendar(mic, start=(now - pd.Timedelta(days=7)).strftime('%Y-%m-%d'))
    tz = str(c.tz)
    d0 = now.tz_convert(tz).date()
    last = c.last_session.date()
    w = max(0, min(DAYS, (last - d0).days + 1))
    if w == 0:
        return None
    end = d0 + dt.timedelta(days=w - 1)
    flat = []
    days = c.sessions_in_range(pd.Timestamp(d0), pd.Timestamp(end)) if c.first_session.date() <= end else []
    have = set()
    for s in days:
        have.add(s.date())
        o, cl = c.session_open(s), c.session_close(s)
        bs, be = c.session_break_start(s), c.session_break_end(s)
        if pd.notna(bs) and pd.notna(be):
            flat += [minutes(o, d0, tz), minutes(bs, d0, tz), minutes(be, d0, tz), minutes(cl, d0, tz)]
        else:
            flat += [minutes(o, d0, tz), minutes(cl, d0, tz)]
    mask = str(getattr(c, 'weekmask', '1111100'))
    hol = [i for i in range(w) if mask[(d0 + dt.timedelta(days=i)).weekday()] == '1' and (d0 + dt.timedelta(days=i)) not in have]
    return {'tz': tz, 'd': d0.isoformat(), 'o': flat, 'w': w, 'hol': hol}


def main():
    os.makedirs(OUT, exist_ok=True)
    now = pd.Timestamp.now(tz='UTC')
    out, missed = [], []
    for mic, (name, city, cc, lat, lng, url) in EXCHANGES.items():
        try:
            s = sessions(mic, now)
        except Exception as e:  # noqa: BLE001 - one exchange's miss is not the run's
            missed.append(f'{mic}: {e}')
            continue
        if s is None:
            missed.append(f'{mic}: its calendar ends before today')
            continue
        out.append({'mic': mic, 'name': name, 'city': city, 'cc': cc, 'lat': lat, 'lng': lng, 'url': url, **s})
    body = {'made': now.strftime('%Y-%m-%dT%H:%MZ'), 'source': f'exchange_calendars {xc.__version__} (Apache-2.0)', 'world': WORLD, 'exchanges': out}
    with open(os.path.join(OUT, 'markets.json'), 'w', encoding='utf-8') as f:
        json.dump(body, f, ensure_ascii=False, separators=(',', ':'))
    short = [e['mic'] for e in out if e['w'] < DAYS]
    print(f'markets: {len(out)} exchanges ({len(short)} with fewer than {DAYS} days known: {" ".join(short)}); missed {len(missed)}: {"; ".join(missed)[:300]}', flush=True)


if __name__ == '__main__':
    t0 = time.time()
    main()
