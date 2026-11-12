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
                 row('https://lemonde.fr/calais', 'Calais un salarie meurt apres une chute dans un entrepot', mc='FR', n=9),
                 row('https://a.fr/x', 'Une histoire sans pays connu pour son site', mc='FR', n=20),
                 row('https://nytimes.com/p', 'Paris court rules on the pension reform appeal', mc='FR', n=3, lg='eng', ds=['nytimes.com', 'lemonde.fr'])]},
          open(os.path.join(h, '40_0.json'), 'w', encoding='utf-8'))
g.write_countries(h, '20500101000000')
top = [s['u'] for s in json.load(open(os.path.join(h, 'country', 'FR.json'), encoding='utf-8'))['top']]
ok(top == ['https://lemonde.fr/calais', 'https://nytimes.com/p', 'https://bbc.co.uk/royal', 'https://a.fr/x'], "top: stories an outlet based in the country carries come first, then the most carried")
ok(g.home_carried({'d': 'lemonde.fr'}, 'FR') and not g.home_carried({'d': 'bbc.co.uk'}, 'FR') and not g.home_carried({'d': 'a.fr'}, 'FR'), 'home: by the outlet list; an outlet not on it has no country')
print('all good')
