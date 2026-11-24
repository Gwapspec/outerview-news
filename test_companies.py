"""companies.py's rules on made-up rows, no network: python3 -I test_companies.py (exit 1 on the first failure)."""
import importlib.util, json, os, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location('companies', os.path.join(HERE, 'companies.py'))
c = importlib.util.module_from_spec(spec); spec.loader.exec_module(c)
ok = lambda x, m: print(('ok   ' if x else 'FAIL ') + m) or (x or sys.exit(1))

# names as compared
ok(c.stem('Apple Inc.') == 'apple' and c.stem('Deutsche Bank AG') == 'deutsche bank' and c.stem('The Boeing Company') == 'boeing', 'legal endings and a leading The go')
ok(c.stem('Grupo Bimbo, S.A.B. de C.V.') == 'grupo bimbo' and c.stem('Berkshire Hathaway Inc.') == 'berkshire hathaway', 'Mexican and American endings')
ok(c.stem('Samsung Electronics') == 'samsung electronics' and c.stem('Reliance Industries') == 'reliance industries', 'a word that is part of the name stays')
ok(c.stem('Nestlé S.A.') == 'nestle' and c.stem('AT&T Inc.') == 'at and t' and c.stem('Inc') == 'inc', 'accents, &, and a name that is only an ending')

# the index: own names first, shared names dropped, exchanges never
COS = [
    {'id': 'Q312', 'name': 'Apple Inc.', 'alts': ['Apple', 'Apple Computer']},
    {'id': 'Q44', 'name': 'Ford Motor Company', 'alts': ['Ford']},
    {'id': 'Q2', 'name': 'Dell Technologies', 'alts': ['Dell', 'Microsoft']},   # Wikidata's mistake on 2026-11-22
    {'id': 'Q3', 'name': 'Microsoft', 'alts': ['MSFT']},
    {'id': 'Q4', 'name': 'Orange S.A.', 'alts': []},
    {'id': 'Q5', 'name': 'Orange', 'alts': []},
    {'id': 'Q6', 'name': 'Motorola Solutions', 'alts': ['Motorola']},
    {'id': 'Q7', 'name': 'Motorola Mobility', 'alts': ['Motorola']},
    {'id': 'Q8', 'name': 'Nasdaq, Inc.', 'alts': ['Nasdaq']},
    {'id': 'Q9', 'name': '3M', 'alts': []},
]
N = c.names_index(COS)
ok(N['apple'] == 'Q312' and N['apple computer'] == 'Q312', "a company's own name and its other names")
ok(N['microsoft'] == 'Q3' and 'msft' in N, "an own name beats another company's other name (Dell's 'Microsoft')")
ok('orange' not in N, 'an own name two companies share: neither')
ok('motorola' not in N and N['motorola solutions'] == 'Q6' and N['motorola mobility'] == 'Q7', 'another name two companies share is dropped; their own names stay')
ok('nasdaq' not in N and '3m' not in N, 'an exchange and a two-letter name are never matched')

# matching a story
m = lambda t, o, p='', l='': c.match(t, o, p, l, N)  # noqa: E731
ok(m('Apple unveils a thinner iPhone', 'apple inc;foxconn') == ['Q312'], 'in the headline and in the organizations')
ok(m('A thinner iPhone, says a report', 'apple inc') == [], 'in the organizations only: no')
ok(m('Apple pie recipes for the fall', 'food network') == [], 'in the headline only: no')
ok(m('Goodyear, Arizona approves a new park', 'goodyear', '', '3#Goodyear, Arizona, United States#US#USAZ##33.4#-112.3#x#10;') == [], 'a place of the same story is not the company')
ok(m('Harrison Ford returns to the screen', 'ford motor', 'harrison ford') == [], 'a person of the same story is not the company')
ok(m('Ford recalls 300,000 trucks', 'ford motor company') == ['Q44'], 'the carmaker when no Ford is a person here')
ok(m('Dell and Microsoft announce a deal', 'dell technologies;microsoft corp') == ['Q2', 'Q3'], 'two companies, sorted')
ok(m('Nasdaq debut for a chipmaker', 'nasdaq') == [], 'the exchange is not a company in news')
ok(m('Apple x', '', '', '') == [] and c.match('Apple x', 'apple', names={}) == [], 'no organizations, or no list: nothing')
ok(m('Pineapple season starts', 'apple') == [], 'a name inside a word is not the name')

# Wikidata's rows to companies
ROWS = [
    {'c': {'value': 'http://www.wikidata.org/entity/Q66048'}, 'cLabel': {'value': 'Deutsche Bank'}, 'cc': {'value': 'DE'}, 'hqLabel': {'value': 'Frankfurt'}, 'coord': {'value': 'Point(8.682 50.11)'}, 'exLabel': {'value': 'New York Stock Exchange'}, 'exCc': {'value': 'US'}, 'tk': {'value': 'DB'}, 'links': {'value': '70'}, 'alts': {'value': 'German Bank|Deutsche Bank'}},
    {'c': {'value': 'http://www.wikidata.org/entity/Q66048'}, 'cLabel': {'value': 'Deutsche Bank'}, 'cc': {'value': 'DE'}, 'hqLabel': {'value': 'Frankfurt'}, 'coord': {'value': 'Point(8.682 50.11)'}, 'exLabel': {'value': 'Frankfurt Stock Exchange'}, 'exCc': {'value': 'DE'}, 'tk': {'value': 'DBK'}, 'links': {'value': '70'}, 'alts': {'value': 'German Bank|Deutsche Bank'}},
    {'c': {'value': 'http://www.wikidata.org/entity/Q99'}, 'cLabel': {'value': 'Q99'}, 'coord': {'value': 'Point(1 2)'}, 'exLabel': {'value': 'X'}, 'links': {'value': '20'}, 'alts': {'value': ''}},
]
R = c.from_rows(ROWS)
ok(len(R) == 1 and R[0]['id'] == 'Q66048' and R[0]['ex'] == 'Frankfurt Stock Exchange' and R[0]['tk'] == 'DBK', 'one company per id, its home exchange first; no company without an English name')
ok(R[0]['la'] == 50.11 and R[0]['lo'] == 8.682 and R[0]['alts'] == ['German Bank'], 'the point as lat, lng; other names without the name itself')

# today: the tiles' rows that carry co, added up
with tempfile.TemporaryDirectory() as d:
    tiles = os.path.join(d, 'tiles'); os.makedirs(tiles); os.makedirs(os.path.join(d, 'companies'))
    with open(os.path.join(d, 'companies', 'list.json'), 'w') as f:
        json.dump({'updated': '2026-11-24T00:00:00Z', 'c': [{'id': 'Q312', 'name': 'Apple Inc.', 'alts': ['Apple'], 'cc': 'US', 'hq': 'Cupertino', 'la': 37.33, 'lo': -122.03, 'ex': 'Nasdaq', 'tk': 'AAPL'}, {'id': 'Q44', 'name': 'Ford Motor Company', 'alts': ['Ford'], 'cc': 'US', 'hq': 'Dearborn', 'la': 42.3, 'lo': -83.2, 'ex': 'NYSE', 'tk': 'F'}]}, f)
    row = lambda u, t, co, n=1, ds=None: {'u': u, 'd': 'a.com', 't': t, 'ts': '20261124080000', 'lg': 'eng', 'la': 1, 'lo': 2, 'pl': 'X', 'cc': 'US', 'co': co, **({'n': n, 'ds': ds, 'us': ['https://%s/x' % x for x in ds]} if ds else {})}  # noqa: E731
    with open(os.path.join(tiles, '30_-130.json'), 'w') as f:
        json.dump({'s': [row('u1', 'Apple unveils a thinner iPhone', ['Q312'], 3, ['a.com', 'b.com', 'c.com']), row('u2', 'Apple unveils a thinner iPhone', ['Q312']), row('u3', 'Ford recalls trucks', ['Q44']), row('u4', 'No company here', [])]}, f)
    with open(os.path.join(tiles, 'top.json'), 'w') as f:
        json.dump({'s': [row('u9', 'Apple something else', ['Q312'])]}, f)  # not a tile: not read
    n = c.today(tiles)
    out = json.load(open(os.path.join(tiles, 'companies.json')))
    ok(n == 2 and [x['id'] for x in out['c']] == ['Q312', 'Q44'], 'two companies, the most carried first')
    a = out['c'][0]
    ok(a['n'] == 1 and a['nl'] == 3 and a['s'][0]['u'] == 'u1' and a['hq'] == 'Cupertino' and a['ex'] == 'Nasdaq', "one row per headline (the most carried copy), the company's head office and exchange")
    ok('im' not in a['s'][0] and a['s'][0]['ds'] == ['a.com', 'b.com', 'c.com'], 'slim rows: no image, the outlets named')
print('all good')
