"""Companies in the news, where they are based (world-view docs/COMPANY-NEWS.md, Game Plan row 80).

Two jobs, both run by news.yml:
  python3 -I companies.py refresh out/companies   once a week: the listed companies, from Wikidata (CC0): listed on an
                                                   exchange (P414, a listing with no end), a head office (P159) with a
                                                   point (P625), known in 20 or more Wikipedia languages, not closed
                                                   (P576) or replaced (P1366). Kept in out/companies/list.json. A
                                                   query that fails keeps the old list.
  python3 -I companies.py today out/tiles          every run: which companies today's stories name, each with its
                                                   most carried stories, in out/tiles/companies.json.
gkg.py imports this file: as it reads GDELT's files it marks each story with the companies its headline names (`co`,
their Wikidata ids), by the rules below; `today` adds those rows up.

The rules (measured on 2026-11-22: 0.7% of stories, 71 companies in an afternoon; 1 of the 15 most carried was the
wrong company): a company is named when its name, or another name of its own, is in the headline AND among GDELT's
organizations for the story (V1Organizations; the headline alone takes "Apple" the fruit, the organizations alone
take "said the New York Times"). Names are compared after dropping legal endings (Inc, plc, AG, Group, Holdings...).
A company's own name wins over another company's other name; another name two companies share is dropped, and so is
an own name two companies share. A name that is also a person or a place in the same story is skipped ("Goodyear,
Arizona"; a Ford who is not the carmaker). The exchanges' own names (Nasdaq, NYSE...) are never companies in news
("debuts on Nasdaq"). A name under three letters is not matched (HP, 3M: missed, not mistaken).

What this cannot do: see a company in a story whose headline does not name it; read a company's name in another
script (the names are Wikidata's English labels); know a head office better than Wikidata; be right every time.
"""
import json, os, re, sys, unicodedata, urllib.parse, urllib.request
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # `python3 -I` leaves the script's folder off the path; gkg.py lives beside this file

ENDPOINT = 'https://query.wikidata.org/sparql'
UA = 'OuterView news job (https://outerview.world)'
REFRESH_DAYS = 7
MIN_SITELINKS = 20
TOP_STORIES = 8   # stories kept per company in companies.json, the most carried first
OUTLETS = 8       # outlets named per story there
ALTS = 8          # other names kept per company
QUERY = '''SELECT ?c ?cLabel ?cc ?hqLabel ?coord ?exLabel ?exCc ?tk ?links (GROUP_CONCAT(DISTINCT ?alt; separator="|") AS ?alts) WHERE {
  ?c p:P414 ?ls . ?ls ps:P414 ?ex . FILTER NOT EXISTS { ?ls pq:P582 ?end }
  OPTIONAL { ?ls pq:P249 ?tk }
  OPTIONAL { ?ex wdt:P17 ?exCountry . ?exCountry wdt:P297 ?exCc }
  ?c wdt:P159 ?hq . ?hq wdt:P625 ?coord .
  OPTIONAL { ?hq wdt:P17 ?country . ?country wdt:P297 ?cc }
  ?c wikibase:sitelinks ?links . FILTER(?links >= %d)
  FILTER NOT EXISTS { ?c wdt:P576 ?d } FILTER NOT EXISTS { ?c wdt:P1366 ?r }
  OPTIONAL { ?c skos:altLabel ?alt FILTER(LANG(?alt) = "en") }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
} GROUP BY ?c ?cLabel ?cc ?hqLabel ?coord ?exLabel ?exCc ?tk ?links''' % MIN_SITELINKS

# Legal and corporate endings dropped from a name before it is compared ("Apple Inc." and "Apple" are one name).
ENDINGS = {'inc', 'incorporated', 'corp', 'corporation', 'co', 'company', 'ltd', 'limited', 'plc', 'ag', 'se', 'sa', 'nv',
           'gmbh', 'group', 'holding', 'holdings', 'llc', 'lp', 'kk', 'oyj', 'ab', 'asa', 'spa', 'bhd', 'berhad', 'tbk', 'pjsc',
           'jsc', 'ojsc', 'pcl', 'bv', 'nyrt', 'ltda', 'sab de cv', 'sa de cv', 'a s', 'the'}
# The exchanges and their operators: in news their names mean the market, not the company.
EXCHANGES = {'nasdaq', 'nyse', 'new york stock exchange', 'euronext', 'deutsche borse', 'deutsche boerse', 'london stock exchange',
             'lse', 'hkex', 'hong kong exchanges and clearing', 'hong kong exchanges', 'japan exchange', 'jpx', 'tmx', 'cme', 'cboe',
             'cboe global markets', 'ice', 'intercontinental exchange', 'singapore exchange', 'sgx', 'asx', 'b3', 'six', 'moex',
             'moscow exchange', 'nse', 'bse', 'bolsa mexicana de valores', 'nasdaq stock market', 'cme group', 'tmx group',
             'stock exchange', 'ftse', 'dow jones', 's and p', 'msci'}
QID = re.compile(r'^Q\d+$')
POINT = re.compile(r'Point\(([-\d.eE]+) ([-\d.eE]+)\)')

NAMES = {}      # folded name -> Wikidata id (the index gkg.py matches against)
BY_ID = {}      # Wikidata id -> its names in that index
COMPANIES = {}  # Wikidata id -> the company's row of list.json


def fold(s):
    """Lower case, no accents, no dots ("U.S. Steel", "S.A.B. de C.V."), '&' as 'and', one space between the letters and
    digits of any script."""
    s = unicodedata.normalize('NFKD', str(s or '')).replace('.', '')
    s = ''.join(ch for ch in s if not unicodedata.combining(ch)).lower().replace('&', ' and ')
    return re.sub(r'[^\w]+', ' ', s).replace('_', ' ').strip()


def stem(name):
    """The name as it is compared: folded, without legal endings at the end and 'the' at the start."""
    words = fold(name).split()
    changed = True
    while changed and len(words) > 1:
        changed = False
        for n in (3, 2, 1):
            if len(words) > n and ' '.join(words[-n:]) in ENDINGS:
                words = words[:-n]
                changed = True
                break
    if len(words) > 1 and words[0] == 'the':
        words = words[1:]
    return ' '.join(words)


def usable(name):
    return len(name) >= 3 and not name.isdigit() and name not in EXCHANGES


def names_index(companies):
    """Folded names to match: a company's own name when no other company has it, then other names no other company
    has and that are not a company's own name. Nothing under three letters, nothing that is an exchange."""
    own, alts = {}, {}
    for c in companies:
        s = stem(c.get('name', ''))
        own.setdefault(s, []).append(c['id'])
        for a in c.get('alts') or []:
            t = stem(a)
            if t and t != s:
                alts.setdefault(t, set()).add(c['id'])
    names = {}
    for s, ids in own.items():
        if len(ids) == 1 and usable(s):
            names[s] = ids[0]
    for t, ids in alts.items():
        if t in own or len(ids) != 1 or not usable(t):
            continue
        names[t] = next(iter(ids))
    return names


def names_by_id(names):
    by = {}
    for name, q in names.items():
        by.setdefault(q, set()).add(name)
    return by


def load_list(path):
    """The list for a run (gkg.py calls this before it reads any file). No list: nothing is matched."""
    global NAMES, BY_ID, COMPANIES
    try:
        with open(path, encoding='utf-8') as f:
            rows = json.load(f).get('c') or []
    except Exception:  # noqa: BLE001
        rows = []
    COMPANIES = {c['id']: c for c in rows if isinstance(c, dict) and c.get('id')}
    NAMES = names_index(COMPANIES.values())
    BY_ID = names_by_id(NAMES)
    return len(COMPANIES)


def location_names(field):
    """The place names in V2Locations (Type#Name#CC#...;), folded."""
    out = []
    for loc in (field or '').split(';'):
        p = loc.split('#')
        if len(p) > 1 and p[1]:
            out.append(fold(p[1].split(',')[0]))
    return ' | '.join(out)


def match(title, orgs_field, persons_field='', locations_field='', names=None):
    """The companies a story names: in GDELT's organizations and in the headline, not a person or a place of the
    same story. Their ids, sorted, three at most; [] when none."""
    by = BY_ID if names is None else names_by_id(names)
    names = NAMES if names is None else names
    if not names or not orgs_field:
        return []
    found = []
    for o in orgs_field.split(';'):
        q = names.get(stem(o))
        if q and q not in found:
            found.append(q)
    if not found:
        return []
    ft = f' {fold(title)} '
    people = f' {fold(persons_field)} '
    places = f' {location_names(locations_field)} '
    out = []
    for q in found:
        # Any of the company's names in the headline ("Ford" for Ford Motor Company), as long as that word is not a
        # person or a place of the same story.
        if any(f' {name} ' in ft and f' {name} ' not in people and f' {name} ' not in places for name in by.get(q, ())):
            out.append(q)
    return sorted(out)[:3]


def from_rows(rows):
    """Wikidata's answer rows (one per listing) to one company each: the listing on a home exchange first, else the
    first; other names eight at most, none that is the name itself; no company without an English name."""
    by = {}
    for r in rows:
        v = lambda k: (r.get(k) or {}).get('value', '')  # noqa: E731
        qid = v('c').rsplit('/', 1)[-1]
        name = v('cLabel').strip()
        m = POINT.match(v('coord'))
        if not QID.match(qid) or not name or QID.match(name) or not m:
            continue
        c = by.get(qid)
        if c is None:
            alts = []
            for a in v('alts').split('|'):
                a = a.strip()
                if a and a != name and len(a) <= 60 and a not in alts and not QID.match(a):
                    alts.append(a)
            c = by[qid] = {'id': qid, 'name': name[:80], 'alts': alts[:ALTS], 'cc': v('cc'), 'hq': v('hqLabel')[:60],
                           'la': round(float(m.group(2)), 3), 'lo': round(float(m.group(1)), 3), 'links': int(v('links') or 0), '_ls': []}
        ex, tk, excc = v('exLabel').strip(), v('tk').strip(), v('exCc')
        if ex and not QID.match(ex):
            c['_ls'].append((excc == c['cc'] and bool(c['cc']), ex[:60], tk[:12]))
    out = []
    for c in by.values():
        ls = sorted(c.pop('_ls'), key=lambda x: not x[0])
        c['ex'] = ls[0][1] if ls else ''
        c['tk'] = ls[0][2] if ls else ''
        out.append(c)
    out.sort(key=lambda c: (-c['links'], c['name']))
    return out


def refresh(folder):
    """The weekly list. Fresh enough: nothing asked. A query that fails leaves the old list in place."""
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, 'list.json')
    try:
        with open(path, encoding='utf-8') as f:
            old = json.load(f)
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(old['updated'].replace('Z', '+00:00'))).days
        if age < REFRESH_DAYS and old.get('c'):
            print(f'companies: list is {age} days old, {len(old["c"])} companies, not asked')
            return len(old['c'])
    except Exception:  # noqa: BLE001
        pass
    req = urllib.request.Request(f'{ENDPOINT}?{urllib.parse.urlencode({"query": QUERY})}', headers={'User-Agent': UA, 'Accept': 'application/sparql-results+json'})
    try:
        with urllib.request.urlopen(req, timeout=150) as r:
            rows = json.load(r)['results']['bindings']
    except Exception as e:  # noqa: BLE001
        print('companies: Wikidata did not answer, the old list stays:', e)
        return 0
    out = from_rows(rows)
    if len(out) < 500:
        print(f'companies: only {len(out)} companies came back, the old list stays')
        return 0
    with open(path, 'w', encoding='utf-8') as f:
        json.dump({'updated': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'), 'source': 'Wikidata (CC0)', 'n': len(out), 'c': out}, f, ensure_ascii=False, separators=(',', ':'))
    print(f'companies: {len(out)} listed companies with a head office, from {len(rows)} listings')
    return len(out)


NOT_TILES = {'state.json', 'index.json', 'top.json', 'launches.json', 'money.json', 'politics.json', 'outer-index.json', 'outer-index-history.json', 'companies.json'}


def slim(s, nl):
    r = {k: s[k] for k in ('u', 'd', 't', 'ts', 'lg', 'la', 'lo', 'pl', 'cc') if k in s}
    r['n'] = s.get('n', 1)
    r['nl'] = nl
    for k in ('ds', 'us', 'dc'):
        if s.get(k):
            r[k] = s[k][:OUTLETS]
    return r


def today(tiles_dir):
    """companies.json: every company a story of the last day names (the tiles' rows that carry `co`), the most
    carried first, each with its stories. Needs the list for the names and head offices."""
    import gkg  # noqa: PLC0415  (gkg imports this file; by now both are loaded)
    n = load_list(os.path.join(os.path.dirname(os.path.abspath(tiles_dir)), 'companies', 'list.json'))
    stories = {}
    for name in sorted(os.listdir(tiles_dir)):
        if not name.endswith('.json') or name in NOT_TILES:
            continue
        try:
            with open(os.path.join(tiles_dir, name), encoding='utf-8') as f:
                rows = json.load(f).get('s') or []
        except Exception:  # noqa: BLE001
            continue
        for s in rows:
            for q in s.get('co') or []:
                if q in COMPANIES:
                    stories.setdefault(q, []).append(s)
    out = []
    for q, rows in stories.items():
        best = {}
        for s in rows:  # one row per headline, the most carried copy
            key = gkg.title_key(s['t'])
            if key not in best or gkg.most_carried(s) > gkg.most_carried(best[key]):
                best[key] = s
        ranked = sorted(best.values(), key=gkg.most_carried, reverse=True)
        c = COMPANIES[q]
        top = [slim(s, gkg.separate(s) if s.get('n', 1) > 1 else 1) for s in ranked[:TOP_STORIES]]
        out.append({'id': q, 'name': c['name'], 'cc': c.get('cc', ''), 'hq': c.get('hq', ''), 'la': c.get('la'), 'lo': c.get('lo'),
                    'ex': c.get('ex', ''), 'tk': c.get('tk', ''), 'n': len(ranked), 'nl': max(r['nl'] for r in top), 's': top})
    out.sort(key=lambda c: (c['nl'], c['n'], c['name']), reverse=True)
    with open(os.path.join(tiles_dir, 'companies.json'), 'w', encoding='utf-8') as f:
        json.dump({'updated': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'), 'source': 'GDELT; Wikidata (CC0)', 'listed': n, 'c': out}, f, ensure_ascii=False, separators=(',', ':'))
    print(f'companies in the news: {len(out)} of {n} listed; {sum(1 for c in out if c["nl"] >= 3)} with 3 or more separate links')
    return len(out)


if __name__ == '__main__':
    what, where = (sys.argv + ['', ''])[1:3]
    if what == 'refresh' and where:
        refresh(where)
    elif what == 'today' and where:
        today(where)
    else:
        print('usage: companies.py refresh <out/companies> | today <out/tiles>')
        sys.exit(2)
