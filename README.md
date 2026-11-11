# outerview-news

[![The Outer Index today](https://outerview.world/api/outer-index/badge.svg)](https://outerview.world/outer-index)

The news job for [OuterView](https://outerview.world), a globe that shows what is happening in any place. It also
builds [the Outer Index](https://outerview.world/outer-index), one number per city for how loud the world is there
today (`index.py`, `tiles/outer-index.json`, the day-by-day `tiles/outer-index-history.json`, CC BY 4.0, as a
[feed](https://outerview.world/outer-index/feed.xml), a [badge](https://outerview.world/api/outer-index/badge.svg?city=fr/paris) and an
[embed box](https://outerview.world/embed/outer-index)).

Every 15 minutes a GitHub Actions workflow reads the newest [GDELT](https://www.gdeltproject.org) GKG files
(English and translated), keeps each story's headline, outlet, link, language, image and first city-level
location, and writes one small JSON file per 10-degree tile with the last 24 hours of stories. The files are
published on the `data` branch, which is rewritten each run so the repository stays small.

- `gkg.py`: the job. `python3 -I gkg.py <out_dir>` merges into what is already there.
- `test_gkg.py`: its rules on made-up stories. `python3 -I test_gkg.py`.
- `outlet-countries.tsv`: where each news site is based (site, GDELT country code), trimmed from the GDELT
  Project's list of news outlets by country (May 2018 update). It is GDELT's estimate, from the places each site
  wrote about most. It is old and it can be wrong; a site that is not on it has no country.
- `.github/workflows/news.yml`: the schedule.
- Data: `https://raw.githubusercontent.com/Gwapspec/outerview-news/data/tiles/<lat10>_<lng10>.json`
  (`index.json` lists the tiles). Fields: `u` url, `d` outlet domain, `t` title, `la`/`lo` location, `pl` place
  name, `cc` country, `ct` GDELT location type, `ts` YYYYMMDDHHMMSS UTC, `lg` language, `im` image, `tn` tone.
- One story, every outlet. The same headline from several outlets is one row: `n` how many outlets carried it
  (outlets, not copies), `ds` their domains (the first is `d`, up to 40), `us` each one's own link in the same
  order ('' for an outlet listed before 2026-11-11, when links were not kept), `dc` the country each is based
  in, in the same order ('' when not known; left off when none is). A headline is matched in any script: lower
  case, letters and digits, the first 70 characters.
- Topic files, the last 24 hours for the whole world, newest first, one row per headline:
  - `tiles/money.json`: money news. A story is in when GDELT's topic marks fall in two or more money groups
    and one of them is a core group. At most 40 per country. Extra fields: `mg` money groups, `mc` the country
    the story names most.
  - `tiles/politics.json`: politics news. A story is in when its marks fall in two or more of the core groups
    (a vote, a party, a law or a lawmaker), three or more groups in all, a core mark sits in the first 700
    characters, and core marks are at least 5% of all its marks. At most 40 per country: half the stories most
    outlets carry, half the newest. Extra fields: `pg` politics groups, `mc` the country the story names most.
  - Nobody picks the stories and no outlet is rated: the tests read GDELT's marks and nothing else. Country
    codes are GDELT's (FIPS), not ISO: the United Kingdom is `UK`, Germany `GM`, China `CH`.

Headline and link only, never the article text. Cite GDELT. Code: MIT.
