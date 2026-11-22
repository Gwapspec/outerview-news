"""Kind and owner of the news sites (world-view docs/WHO-CARRIED.md, Game Plan row 79).

Wikidata's items whose official website (P856) is the site; their "instance of" (P31) sorted into a few kinds (news
agency, TV, radio, newspaper, magazine, online); and who owns them now (P127 owned by, else P749 parent organization,
never a statement with an end time). Wikidata is CC0.

The news job runs this before the tiles are built: python3 -I kinds.py out/tiles. It counts the sites named on rows
several outlets carried, asks only about sites it has not asked about (the most seen first, at most LOOKUP a run), and
keeps every answer in out/outlets/kinds.tsv (site, kind, owner, item, day asked), which gkg.py reads. A site Wikidata
does not know is kept with no kind and asked again after RETRY days, so a run with nothing new asks nothing.

What this cannot do: name a kind or owner Wikidata lacks, or fix one it has wrong. Only a few kinds are named; any
other class ("periodical", "company") gives no kind. Nothing here rates a site.
"""
import json, os, re, sys, time, urllib.error, urllib.parse, urllib.request
from datetime import datetime, timedelta, timezone

ENDPOINT = 'https://query.wikidata.org/sparql'
UA = 'OuterView news job (https://outerview.world)'
LOOKUP = 600    # sites asked about per run, the most seen first (300 took 9 seconds on 2026-11-22)
BATCH = 60      # sites per query (each with 8 spellings of its address)
RETRY = 30      # days before a site Wikidata did not know is asked again
REFRESH = 60    # days before a known site is asked again
FORGET = 180    # days after which a site that was not asked again (no row names it) is dropped
TIME_CAP = 100  # seconds for all the queries of a run
# First match wins, in this order (the kinds measured on 2026-11-22: 71% of the day's outlets have one).
KINDS = (
    ('agency', re.compile(r'news agency|press agency', re.I)),
    ('tv', re.compile(r'television|TV channel|news channel|broadcast network|specialty channel', re.I)),
    ('radio', re.compile(r'radio', re.I)),
    ('paper', re.compile(r'newspaper', re.I)),
    ('mag', re.compile(r'magazine', re.I)),
    ('web', re.compile(r'website|web portal|news portal|online', re.I)),
)
RANK = {'agency': 0, 'tv': 1, 'radio': 2, 'paper': 3, 'mag': 4, 'web': 5, '': 9}
QID = re.compile(r'^Q\d+$')
HOST = re.compile(r'^[a-z0-9.-]+\.[a-z]{2,}$')


def kind_of(classes):
    """The kind for a set of class names ('' when none of them is one of the kinds)."""
    for kind, rx in KINDS:
        if any(rx.search(c) for c in classes):
            return kind
    return ''


def clean(text):
    return re.sub(r'[\t\r\n]+', ' ', text or '').strip()


def pick_owner(found):
    """found: (prop, preferred, label) for each current owner statement. P127 (owned by) before P749 (parent
    organization), a preferred statement before a normal one. Two or more left is no owner: Wikidata then often
    lists part owners or mixes up "owner of" (2026-11-22: hna.de "owned by" two radio stations it owns shares in)."""
    good = [(p, pref, clean(l)) for p, pref, l in found if l and not QID.match(l)]
    if not good:
        return ''
    best = min((p != 'P127', not pref) for p, pref, _ in good)
    names = {l for p, pref, l in good if (p != 'P127', not pref) == best}
    return names.pop() if len(names) == 1 else ''


def spellings(site):
    return [f'{s}://{w}{site}{e}' for s in ('https', 'http') for w in ('www.', '') for e in ('/', '')]


def host_of(url):
    h = urllib.parse.urlsplit(url).hostname or ''
    return h[4:] if h.startswith('www.') else h


def ask(query, deadline):
    if time.time() > deadline:
        raise TimeoutError('time cap reached')
    body = urllib.parse.urlencode({'query': query}).encode()
    req = urllib.request.Request(ENDPOINT, data=body, headers={'User-Agent': UA, 'Accept': 'application/sparql-results+json', 'Content-Type': 'application/x-www-form-urlencoded'})
    with urllib.request.urlopen(req, timeout=max(5, min(45, deadline - time.time()))) as r:
        return json.load(r)['results']['bindings']


def lookup(sites, deadline):
    """({site: (kind, owner, item)} for the sites Wikidata knows, [the sites fully asked about]). A query that fails
    or runs past the deadline stops the run: the batches before it count, and nothing after it is marked asked."""
    per = {}  # site -> {item: set(class names)}
    done = []
    for i in range(0, len(sites), BATCH):
        batch = sites[i:i + BATCH]
        vals = ' '.join(f'<{u}>' for s in batch for u in spellings(s))
        # Plain English labels, not the label service: with it a batch took over 45 seconds (2026-11-22).
        q = ('SELECT ?site ?item ?cl WHERE { VALUES ?site { %s } ?item wdt:P856 ?site . '
             'OPTIONAL { ?item wdt:P31 ?cls . ?cls rdfs:label ?cl . FILTER(LANG(?cl) = "en") } }' % vals)
        try:
            got = ask(q, deadline)
        except (urllib.error.URLError, TimeoutError, OSError, ValueError, KeyError) as e:
            print('Wikidata lookup stopped:', e)
            break
        for b in got:
            site = host_of(b['site']['value'])
            item = b['item']['value'].rsplit('/', 1)[-1]
            per.setdefault(site, {}).setdefault(item, set())
            if 'cl' in b:
                per[site][item].add(b['cl']['value'])
        done += batch
        time.sleep(0.5)
    chosen = {}
    for site, items in per.items():
        # The item that names the kind best (a newspaper's own item over its company's); the lowest number on a tie.
        item = min(items, key=lambda it: (RANK[kind_of(items[it])], int(it[1:]) if QID.match(it) else 1 << 62))
        chosen[site] = (kind_of(items[item]), item)
    owners = {}
    ids = sorted({it for _, it in chosen.values() if QID.match(it)})
    for i in range(0, len(ids), 150):
        vals = ' '.join('wd:' + it for it in ids[i:i + 150])
        q = ('SELECT ?item ?p ?rank ?end ?ol WHERE { VALUES ?item { %s } VALUES (?p ?ps) { (p:P127 ps:P127) (p:P749 ps:P749) } '
             '?item ?p ?st . ?st ?ps ?o ; wikibase:rank ?rank . OPTIONAL { ?st pq:P582 ?end } '
             'OPTIONAL { ?o rdfs:label ?ol . FILTER(LANG(?ol) = "en") } }' % vals)
        try:
            got = ask(q, deadline)
        except (urllib.error.URLError, TimeoutError, OSError, ValueError, KeyError) as e:
            print('Wikidata owners stopped, so this run keeps nothing:', e)
            return {}, []
        for b in got:
            rank = b['rank']['value']
            if 'end' in b or rank.endswith('DeprecatedRank'):  # a former owner, or a statement marked wrong
                continue
            it = b['item']['value'].rsplit('/', 1)[-1]
            prop = b['p']['value'].rsplit('/', 1)[-1]
            owners.setdefault(it, []).append((prop, rank.endswith('PreferredRank'), b.get('ol', {}).get('value', '')))
        time.sleep(0.5)
    return {site: (kind, pick_owner(owners.get(item, [])), item) for site, (kind, item) in chosen.items()}, done


def load(path):
    out = {}
    try:
        with open(path, encoding='utf-8') as f:
            for line in f:
                p = line.rstrip('\n').split('\t')
                if len(p) == 5 and not line.startswith('#'):
                    out[p[0]] = tuple(p[1:])
    except OSError:
        pass
    return out


def save(path, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        f.write('# site\tkind\towner\twikidata item\tday asked (Wikidata, CC0; world-view docs/WHO-CARRIED.md)\n')
        for site in sorted(rows):
            f.write('\t'.join((site,) + tuple(rows[site])) + '\n')
    os.replace(tmp, path)


def sites_in(tiles_dir):
    """How many rows carried by several outlets name each site, over every file in the tiles folder."""
    seen = {}
    for name in os.listdir(tiles_dir):
        if not name.endswith('.json') or name == 'state.json':
            continue
        try:
            with open(os.path.join(tiles_dir, name), encoding='utf-8') as f:
                rows = json.load(f).get('s', [])
        except Exception:  # noqa: BLE001
            continue
        for s in rows:
            for d in s.get('ds') or []:
                d = (d or '').strip().lower()
                d = d[4:] if d.startswith('www.') else d
                if HOST.match(d):
                    seen[d] = seen.get(d, 0) + 1
    return seen


def due(row, today):
    """Whether a kept answer should be asked again: an unknown site after RETRY days, a known one after REFRESH."""
    try:
        day = datetime.strptime(row[3], '%Y-%m-%d').date()
    except ValueError:
        return True
    return (today - day).days >= (REFRESH if row[2] else RETRY)


def main(tiles_dir):
    path = os.path.join(os.path.dirname(os.path.abspath(tiles_dir)), 'outlets', 'kinds.tsv')
    today = datetime.now(timezone.utc).date()
    rows = load(path)
    seen = sites_in(tiles_dir) if os.path.isdir(tiles_dir) else {}
    todo = sorted((s for s in seen if s not in rows or due(rows[s], today)), key=lambda s: (-seen[s], s))[:LOOKUP]
    asked = 0
    if todo:
        found, done = lookup(todo, time.time() + TIME_CAP)
        for s in done:
            kind, owner, item = found.get(s, ('', '', ''))
            rows[s] = (kind, owner, item, today.isoformat())
        asked = len(done)
    cut = (today - timedelta(days=FORGET)).isoformat()
    rows = {s: r for s, r in rows.items() if r[3] >= cut}
    save(path, rows)
    known = sum(1 for r in rows.values() if r[2])
    print(f'sites seen {len(seen)}, asked {asked}, kept {len(rows)}, on Wikidata {known}, with a kind {sum(1 for r in rows.values() if r[0])}, with an owner {sum(1 for r in rows.values() if r[1])}')


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else 'out/tiles')
