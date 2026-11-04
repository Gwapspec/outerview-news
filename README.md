# outerview-news

The news job for [OuterView](https://outerview.pages.dev), a globe that shows what is happening in any place.

Every 15 minutes a GitHub Actions workflow reads the newest [GDELT](https://www.gdeltproject.org) GKG files
(English and translated), keeps each story's headline, outlet, link, language, image and first city-level
location, and writes one small JSON file per 10-degree tile with the last 24 hours of stories. The files are
published on the `data` branch, which is rewritten each run so the repository stays small.

- `gkg.py`: the job. `python3 -I gkg.py <out_dir>` merges into what is already there.
- `.github/workflows/news.yml`: the schedule.
- Data: `https://raw.githubusercontent.com/Gwapspec/outerview-news/data/tiles/<lat10>_<lng10>.json`
  (`index.json` lists the tiles). Fields: `u` url, `d` outlet domain, `ds` other outlets with the same headline,
  `n` outlet count, `t` title, `la`/`lo` location, `pl` place name, `cc` country, `ct` GDELT location type,
  `ts` YYYYMMDDHHMMSS UTC, `lg` language, `im` image, `tn` tone.

Headline and link only, never the article text. Cite GDELT. Code: MIT.
