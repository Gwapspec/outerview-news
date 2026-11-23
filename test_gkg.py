"""The news job's rules on made-up stories: python3 -I test_gkg.py (exit 1 on the first failure)."""
import importlib.util, json, os, sys, tempfile
spec = importlib.util.spec_from_file_location('gkg', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'gkg.py'))
g = importlib.util.module_from_spec(spec); spec.loader.exec_module(g)
ok = lambda c, m: print(('ok   ' if c else 'FAIL ') + m) or (c or sys.exit(1))
# outlet countries
ok(g.outlet_country('www.bbc.co.uk') == 'UK', 'bbc.co.uk is UK (FIPS)')
ok(g.outlet_country('lemonde.fr') == 'FR', 'lemonde.fr is FR')
ok(g.outlet_country('someone.wordpress.com') == '', 'a blog on a shared host has no country')
ok(g.outlet_country('medium.com') == '', 'a shared host has no country')
ok(g.outlet_country('not-a-real-outlet-xyz.example') == '', 'unknown stays unknown')
ok(g.outlet_country('noticias.sapo.pt') == g.outlet_country('sapo.pt') != '', 'a subdomain takes its parent')
ok(g.outlet_country('') == '' and g.outlet_country(None) == '', 'empty is unknown')
# headline keys
ok(g.title_key('النفط يواصل مكاسبه.. برنت يرتفع 3 دولارات') != g.title_key('بيت التمويل يقرع جرس 3 إدراج'), 'two Arabic headlines with the same digit are two stories')
ok(g.title_key('Vote: Senate PASSES bill!') == g.title_key('vote senate passes bill'), 'case and marks do not matter')
ok(g.title_key('三个关键词解读前10个月') != g.title_key('前10个月我国外贸进出口数据'), 'two Chinese headlines are two stories')
# carry: n counts outlets, not copies; links in step
a = {'u': 'https://a.com/1', 'd': 'a.com', 't': 'T'}
g.carry(a, {'u': 'https://a.com/2', 'd': 'a.com'})
ok(a.get('n', 1) == 1 and a['ds'] == ['a.com'], 'the same outlet twice is one outlet')
g.carry(a, {'u': 'https://lemonde.fr/x', 'd': 'lemonde.fr'})
ok(a['n'] == 2 and a['us'] == ['https://a.com/1', 'https://lemonde.fr/x'], 'a second outlet is counted and linked')
old = {'u': 'https://a.com/1', 'd': 'a.com', 'ds': ['a.com', 'b.com', 'c.com'], 'n': 3, 't': 'T'}
g.carry(old, {'u': 'https://bbc.co.uk/x', 'd': 'bbc.co.uk'})
ok(old['us'] == ['https://a.com/1', '', '', 'https://bbc.co.uk/x'] and old['n'] == 4, 'a row from before links: old outlets have no link, new ones do')
for i in range(60): g.carry(old, {'u': 'https://o%d.com/x' % i, 'd': 'o%d.com' % i})
ok(len(old['ds']) == g.OUTLETS == len(old['us']) and old['n'] == 64, 'names stop at OUTLETS, the count goes on')
g.finish([old, a, {'u': 'u', 'd': 'not-a-real-outlet-xyz.example', 't': 'x'}])
ok(len(old['dc']) == len(old['ds']) and old['dc'][3] == 'UK', 'countries in step with names')
ok(a['dc'] == [g.outlet_country('a.com'), 'FR'], 'dc for a two-outlet row')
# write_topic end to end
d = tempfile.mkdtemp()
mk = lambda u, dom, t, ts='20991231000000': {'u': u, 'd': dom, 't': t, 'la': 1, 'lo': 1, 'pl': 'X', 'cc': 'US', 'ct': '3', 'ts': ts, 'lg': 'eng', 'im': '', 'tn': 0, 'pg': ['vote', 'law'], 'mc': 'US'}
st = [mk('https://nytimes.com/1', 'nytimes.com', 'Senate passes the budget bill after a long night'), mk('https://lemonde.fr/1', 'lemonde.fr', 'Senate passes the budget bill after a long night'), mk('https://x.wordpress.com/1', 'x.wordpress.com', 'Senate passes the budget bill after a long night'), mk('https://nytimes.com/2', 'nytimes.com', 'A different headline about the election count')]
g.write_politics(d, st, '20000101000000')
g.write_politics(d, [mk('https://bbc.co.uk/9', 'bbc.co.uk', 'Senate passes the budget bill after a long night')], '20000101000000')
rows = json.load(open(os.path.join(d, 'politics.json'), encoding='utf-8'))['s']
big = next(r for r in rows if 'ds' in r)
ok(big['n'] == 4 and big['ds'] == ['nytimes.com', 'lemonde.fr', 'x.wordpress.com', 'bbc.co.uk'] and big['dc'] == ['US', 'FR', '', 'UK'] and len(big['us']) == 4, 'a second run adds to the first: 4 outlets, 3 countries, one unknown')
one = next(r for r in rows if 'ds' not in r)
ok(one.get('dc') == ['US'] and 'us' not in one, 'a one-outlet row carries its outlet country')
# country files
c = tempfile.mkdtemp()
row = lambda u, t, cc='FR', mc=None, n=1, ts='20991231000000', lg='fra', **more: dict({'u': u, 'd': u.split('/')[2], 't': t, 'la': 1, 'lo': 1, 'pl': 'X', 'cc': cc, 'ct': '3', 'ts': ts, 'lg': lg, 'im': '', 'tn': 0, 'n': n}, **({'mc': mc} if mc else {}), **more)
put = lambda name, rows: json.dump({'s': rows}, open(os.path.join(c, name), 'w', encoding='utf-8'))
put('40_0.json', [row('https://a.fr/%d' % i, 'Une histoire de France numero %d bien distincte' % i, mc='FR', n=i + 1) for i in range(15)]
    + [row('https://lemonde.fr/copy', 'Une histoire de France numero 14 bien distincte', mc='FR', n=40),
       row('https://b.com/us', 'A story that opens in Paris about America', mc='US', lg='eng'),
       row('https://c.fr/old', 'Une vieille histoire de la semaine derniere', mc='FR', ts='20000101000000'),
       row('https://d.de/1', 'Eine Geschichte aus der Zeit vor dem Landeszeichen', cc='GM', lg='deu'),
       row('https://e.com/1', 'A story placed nowhere in particular at all', cc='', lg='eng')])
put('politics.json', [row('https://a.fr/3', 'Une histoire de France numero 3 bien distincte', mc='FR', pg=['vote']), row('https://p.fr/1', 'Le parlement vote le budget de la nation', mc='FR', pg=['law']), row('https://p.com/2', 'A vote in Paris about Washington', mc='US', lg='eng', pg=['vote'])])
put('money.json', [row('https://m.fr/1', 'La banque centrale garde son taux directeur', mc='FR', mg=['rate'])])
open(os.path.join(c, 'state.json'), 'w').write('{}')
os.makedirs(os.path.join(c, 'country')); open(os.path.join(c, 'country', 'ZZ.json'), 'w').write('{}')
n, total = g.write_countries(c, '20500101000000')
fr = json.load(open(os.path.join(c, 'country', 'FR.json'), encoding='utf-8'))
ok(len(fr['top']) == g.COUNTRY_TOP and fr['top'][0]['u'] == 'https://lemonde.fr/copy' and fr['top'][0]['n'] == 40, 'top: the twelve most carried, one row per headline, the bigger copy kept')
ok(all(s['u'] != 'https://b.com/us' and s['u'] != 'https://c.fr/old' for s in fr['top']), 'top: no story that names another country most, none older than a day')
ok([s['u'] for s in fr['politics']] == ['https://a.fr/3', 'https://p.fr/1'] and [s['u'] for s in fr['money']] == ['https://m.fr/1'], 'politics and money: the rows at home only')
ok(fr['cc'] == 'FR' and fr['source'] == 'GDELT' and 'dc' in fr['top'][0], 'the file names its country and source; top rows carry outlet countries')
ok(os.path.exists(os.path.join(c, 'country', 'GM.json')) and not os.path.exists(os.path.join(c, 'country', 'US.json')), 'a row from before mc counts by its first city; a country only named from abroad gets no file')
ok(not os.path.exists(os.path.join(c, 'country', 'ZZ.json')), 'a country that went quiet loses its file')
idx = json.load(open(os.path.join(c, 'country', 'index.json'), encoding='utf-8'))['c']
ok(n == 2 and set(idx) == {'FR', 'GM'} and idx['GM'] == {'deu': 1}, 'the index lists the countries with a file')
ok(idx['FR'] == {'fra': 14} and total == 15, 'the index counts a story once across the three lists (12 top, of which one is in politics, plus 2)')
os.makedirs(os.path.join(c, 'x'), exist_ok=True)
ok(sorted(n_ for n_ in os.listdir(c) if n_.endswith('.json') and n_ not in g.NOT_TILES) == ['40_0.json'], 'the country folder is not taken for a tile')
# a country's own outlets first
h = tempfile.mkdtemp()
json.dump({'s': [row('https://bbc.co.uk/royal', 'A prince speaks about French wildlife at an awards night', mc='FR', n=33, lg='eng'),
                 row('https://lemonde.fr/calais', 'Calais un salarie meurt apres une chute dans un entrepot', mc='FR', n=9, ds=['lemonde.fr'] + ['o%d.fr' % i for i in range(8)]),
                 row('https://a.fr/x', 'Une histoire sans pays connu pour son site', mc='FR', n=20),
                 row('https://nytimes.com/p', 'Paris court rules on the pension reform appeal', mc='FR', n=3, lg='eng', ds=['nytimes.com', 'lemonde.fr'])]},
          open(os.path.join(h, '40_0.json'), 'w', encoding='utf-8'))
g.write_countries(h, '20500101000000')
top = [s['u'] for s in json.load(open(os.path.join(h, 'country', 'FR.json'), encoding='utf-8'))['top']]
ok(top == ['https://lemonde.fr/calais', 'https://nytimes.com/p', 'https://bbc.co.uk/royal', 'https://a.fr/x'], "top: stories an outlet based in the country carries come first, then the most carried")
ok(g.home_carried({'d': 'lemonde.fr'}, 'FR') and not g.home_carried({'d': 'bbc.co.uk'}, 'FR') and not g.home_carried({'d': 'a.fr'}, 'FR'), 'home: by the outlet list; an outlet not on it has no country')
# token-shaped links (2026-11-13: GitHub's push protection refused a headline link and the news stopped)
ok(bool(g.TOKENISH.search('https://example.pt/noticias/li' + 'p_AbCdEf1234567890xyz')), 'a link shaped like a Lichess token is caught')
ok(bool(g.TOKENISH.search('https://x.com/ghp_' + 'a' * 36)), 'a link shaped like a GitHub token is caught')
ok(not g.TOKENISH.search('https://www.reuters.com/world/asia-pacific/philip_morris-results-2026-11-13/'), 'an ordinary link is kept')
ok(not g.TOKENISH.search('Philippines: skip_the_queue at Manila airport, AIzawl talks'), 'an ordinary headline is kept')
# the search file (world-view docs/NEWS-SEARCH.md, row 75)
f = tempfile.mkdtemp()
json.dump({'s': [row('https://a.com/1', 'Nvidia shares fall', n=3, ds=['a.com', 'b.com', 'c.com']), row('https://a.com/2', 'A cat show in Leeds', n=1)]}, open(os.path.join(f, '50_0.json'), 'w', encoding='utf-8'))
json.dump({'s': [row('https://z.com/9', 'NVIDIA shares FALL!', n=7, ds=['z.com'] + ['s%d.com' % i for i in range(6)]), row('https://p.com/1', 'Old story', n=4, ts='20000101000000')]}, open(os.path.join(f, 'politics.json'), 'w', encoding='utf-8'))
os.makedirs(os.path.join(f, 'country')); json.dump({'top': [row('https://fr.fr/1', 'Une seule source', n=1)]}, open(os.path.join(f, 'country', 'FR.json'), 'w', encoding='utf-8'))
ok(g.write_find(f, '20260101000000') == 2, 'search file: one row per headline, two outlets or more from the tiles, every country row, nothing old')
d = json.load(open(os.path.join(f, 'find', 'news.json'), encoding='utf-8'))
rows = [dict(zip(d['row'], r)) for r in d['s']]
ok(rows[0]['u'] == 'https://z.com/9' and rows[0]['n'] == 7 and rows[1]['t'] == 'Une seule source', 'search file: the most carried copy of a headline is kept, the most carried first')
ok(rows[0]['nl'] == 7 and rows[1]['nl'] == 1, 'search file: separate links beside the outlets (1 for one outlet)')
ok(os.path.isdir(os.path.join(f, 'find')) and 'find.json' not in os.listdir(f), 'search file: in its own folder, never taken for a tile')
# kind and owner of each outlet (world-view docs/WHO-CARRIED.md, row 79)
kf = os.path.join(tempfile.mkdtemp(), 'kinds.tsv')
open(kf, 'w', encoding='utf-8').write('# site\tkind\towner\titem\tday\nlemonde.fr\tpaper\tGroupe Le Monde\tQ12461\t2026-11-22\nbbc.co.uk\ttv\t\tQ9531\t2026-11-22\nunknown.org\t\t\t\t2026-11-22\n')
g.KINDS_FILE, g._kinds = kf, None
r = {'u': 'https://lemonde.fr/1', 'd': 'lemonde.fr', 't': 'T', 'n': 3, 'ds': ['lemonde.fr', 'www.bbc.co.uk', 'x.com'], 'us': ['https://lemonde.fr/1', 'https://bbc.co.uk/2', 'https://x.com/3']}
g.finish([r])
ok(r['dk'] == ['paper', 'tv', ''] and r['do'] == ['Groupe Le Monde', '', ''], 'kind and owner in step with names; www. does not matter; unknown is empty')
one = {'u': 'https://lemonde.fr/1', 'd': 'lemonde.fr', 't': 'T', 'dk': ['paper'], 'do': ['Groupe Le Monde']}
g.finish([one])
ok('dk' not in one and 'do' not in one, 'a row one outlet carried has no kind lists')
nob = {'u': 'https://x.com/1', 'd': 'x.com', 't': 'T', 'n': 2, 'ds': ['x.com', 'unknown.org'], 'us': ['https://x.com/1', 'https://unknown.org/1'], 'dk': ['tv', '']}
g.finish([nob])
ok('dk' not in nob and 'do' not in nob, 'no kind known: both lists left off, an old one removed')
own = {'u': 'https://bbc.co.uk/1', 'd': 'bbc.co.uk', 't': 'T', 'n': 2, 'ds': ['bbc.co.uk', 'x.com'], 'us': ['https://bbc.co.uk/1', 'https://x.com/1']}
g.finish([own])
ok(own['dk'] == ['tv', ''] and 'do' not in own, 'a kind without an owner: dk only')
g.KINDS_FILE, g._kinds = None, None
# separate links (world-view docs/WHO-CARRIED.md, row 79, module 2)
ok(g.link_path('https://www.a.com/News/National/24745123.story/') == '/news/national/24745123.story' and g.link_path('https://a.com/') == '' and g.link_path('https://a.com/news') == '', 'a link path: no site, no trailing slash, lower case; a section page is none')
ok(g.link_path('https://a.com/story.php?id=991') == '/story.php?id=991', 'the query is part of the path')
chain = {'u': 'https://a.co.uk/news/national/24745123.x/', 'd': 'a.co.uk', 't': 'T', 'ts': '20991231000000'}
for i in range(9):
    g.carry(chain, {'u': 'https://c%d.co.uk/news/national/24745123.x/' % i, 'd': 'c%d.co.uk' % i})
g.carry(chain, {'u': 'https://own.com/a-story-of-its-own', 'd': 'own.com'})
g.carry(chain, {'u': 'https://home.com/', 'd': 'home.com'})
ok(chain['n'] == 12 and g.separate(chain) == 3, 'one article on 10 sites is one link: 12 outlets, 3 separate links (a home page counts as its site)')
big = {'u': 'https://a.com/one/article/1', 'd': 'a.com', 't': 'T', 'ts': '20991231000000'}
for i in range(1, g.OUTLETS):
    g.carry(big, {'u': 'https://x%d.com/one/article/1' % i, 'd': 'x%d.com' % i})
for i in range(30):
    g.carry(big, {'u': 'https://y%d.com/one/article/1' % i, 'd': 'y%d.com' % i})
ok(big['n'] == 70 and g.separate(big) == 1 and 'px' not in big, 'past the list, a copy of a listed article adds no link')
for i in range(5):
    g.carry(big, {'u': 'https://z%d.com/own-story-%d' % (i, i), 'd': 'z%d.com' % i})
g.carry(big, {'u': 'https://z9.com/own-story-0', 'd': 'z9.com'})
ok(big['n'] == 76 and g.separate(big) == 6 and len(big['px']) == 5, 'past the list, new links are counted once each')
g.finish([big])
ok(big['nl'] == 6 and len(big['px']) == 5, 'finish writes nl and keeps px')
solo = {'u': 'https://a.com/x/y/z/1', 'd': 'a.com', 't': 'T', 'nl': 4, 'px': ['ab']}
g.finish([solo])
ok('nl' not in solo and 'px' not in solo and g.separate(solo) == 1, 'a story one outlet carried has no nl and counts 1')
ok(g.most_carried({'n': 155, 'ts': '1', 'ds': ['a', 'b'], 'us': ['https://a/same/path/1', 'https://b/same/path/1']}) < g.most_carried({'n': 3, 'ts': '0', 'ds': ['a', 'b', 'c'], 'us': ['https://a/p/one-1', 'https://b/p/two-2', 'https://c/p/three-3']}), 'three separate links outrank one article on 155 sites')
print('all good')
# the pin by evidence (2026-11-23, world-view docs/CORE-PASS.md): a city is the pin only when the text supports it
LOC = lambda typ, name, cc, lat, lng, fid, off: f'{typ}#{name}#{cc}#{cc}00##{lat}#{lng}#{fid}#{off}'
hamlet = ';'.join([LOC(1, 'Brazil', 'BR', -10, -55, 'BR', 40), LOC(4, 'Tres Lagoas, Para, Brazil', 'BR', -1.23, -47.65, '-123', 900)])
p = g.best_location(hamlet, 'Adolescente morre após ser atingida por moto aquática')
ok(p['type'] == '1' and p['name'] == 'Brazil' and 'pm' not in p, 'a town mentioned once, late, not in the headline, not one of our cities: the country is the pin')
named = g.best_location(hamlet, 'Três Lagoas: adolescente morre após acidente')
ok(named['type'] == '4' and named.get('ph') == 1 and named.get('pm') == 1, 'the headline names it (accents aside): the town is the pin, marked named')
twice = ';'.join([LOC(1, 'Japan', 'JA', 36, 138, 'JA', 10), LOC(4, 'Kanagawa, Fukushima, Japan', 'JA', 37.58, 139.92, '-555', 120), LOC(4, 'Kanagawa, Fukushima, Japan', 'JA', 37.58, 139.92, '-555', 800)])
ok(g.best_location(twice, '押田岳が事務所の先輩にキス').get('pm') == 2, 'mentioned twice, the first time early: kept, with its mentions')
known = LOC(4, 'Yokohama, Kanagawa, Japan', 'JA', 35.44, 139.64, '-1', 2000)
ok(g.best_location(known, 'x')['name'].startswith('Yokohama'), 'one of our cities, mentioned once and late: kept (GDELT JA is ISO JP)')
first = ';'.join([LOC(4, 'Berkeley County, South Carolina, United States', 'US', 33.2, -80.0, '-9', 50), LOC(4, 'Charleston, South Carolina, United States', 'US', 32.78, -79.93, '-8', 400)])
ok(g.best_location(first, 'Home Depot plans new Charleston area store')['name'].startswith('Charleston'), 'the city in the headline beats the first city named')
ok(g.best_location(LOC(1, 'France', 'FR', 46, 2, 'FR', 10), 'x')['type'] == '1', 'a story with only a country keeps the country')
state = ';'.join([LOC(5, 'Gauteng, South Africa', 'SF', -26, 28, 'G', 30), LOC(4, 'Mogale, Gauteng, South Africa', 'SF', -26.1, 27.8, '-77', 1500)])
ok(g.best_location(state, 'Mogale City rivals agree on one thing')['name'].startswith('Mogale'), 'a weak town named in the headline is kept')
ok(g.best_location(state, 'Rivals agree on one thing')['type'] == '5', 'with no country named, the state is the pin')
