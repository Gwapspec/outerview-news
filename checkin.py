# Tell Sentry's cron monitor "news-clock" that the news went out. Sentry opens an issue (and emails) when no
# word comes for 35 minutes, so the news clock is watched from outside GitHub.
# No key is stored here: the address is built from the public Sentry DSN the site already hands every browser
# (/api/config). If the site is down the check-in fails too, which is a true alarm.
import json
import re
import sys
import urllib.request

UA = {'User-Agent': 'OuterView news job'}


def get(url):
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=20)


def main():
    cfg = json.load(get('https://outerview.world/api/config'))
    m = re.match(r'https://([0-9a-f]+)@([^/]+)/(\d+)$', cfg.get('sentryDsn') or '')
    if not m:
        sys.exit('no Sentry DSN in /api/config')
    key, host, project = m.groups()
    r = get(f'https://{host}/api/{project}/cron/news-clock/{key}/?status=ok')
    print('check-in', r.status)


if __name__ == '__main__':
    main()
