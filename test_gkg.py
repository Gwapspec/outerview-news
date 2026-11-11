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
print('all good')
