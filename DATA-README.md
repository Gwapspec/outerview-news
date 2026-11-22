# OuterView news tiles

Built every 15 minutes from the GDELT Project's GKG files by the workflow in the `main` branch of this
repository. One JSON file per 10-degree tile, the last 24 hours of stories, headline and link only. Data: GDELT
Project (cite GDELT). Used by https://outerview.world.

`tiles/money.json` and `tiles/politics.json` hold the last 24 hours of money news and politics news for the whole
world, chosen by GDELT's topic marks (the rules are in the `main` branch's README). Nobody picks the stories.

A story several outlets carried is one row that lists them: `ds` the outlets, `us` each one's own link, `dc` the
country each is based in. The countries come from the GDELT Project's list of news outlets by country (May 2018);
they are GDELT's estimate and can be wrong, and an outlet that is not on the list has none. `dk` and `do`, in the same
order, are each outlet's kind (`agency`, `tv`, `radio`, `paper`, `mag`, `web`) and owner where Wikidata says, `''` where
it does not; each is left off when none is known. `nl` is how many separate links ran the story: sites that run one
article under the same link path count once (`px` keeps a short key for each new link past the 40 listed). Every
"most carried" order here (top.json, the topic files, a country's top, the search file) ranks by `nl`, then `n`.

`outlets/kinds.tsv` is what Wikidata said about each news site (CC0): its kind, its owner (owned by, else parent
organization, a current statement only, and only when Wikidata names one), its item and the day it was asked. A site
Wikidata does not know is kept with no item and asked again after 30 days. Nothing here rates an outlet.

`tiles/country/<cc>.json` is one country's news at home in the last 24 hours (`cc` is GDELT's FIPS country code): `top`
its stories (those an outlet based there carries first, then the most carried), `politics` and `money` its rows of the two topic files. A story is a country's own when
its first city is there and it names that country most. `tiles/country/index.json` counts each country's stories
by language.
`tiles/find/news.json` is the day's most carried stories for the site's news search, one row per headline, each row
a short list in the order its `row` field gives.

## wind/

The wind for OuterView's Wind layer (world-view `docs/WIND.md`), from NOAA's GFS model (public domain), refreshed when
a new run is out (00, 06, 12 and 18 UTC, about 3.5 hours later), by `wind.py` in the news job.

- `wind/latest.png`: 360 x 181 pixels, 8-bit RGB. Red is the wind toward the east (u), green toward the north (v), each
  0 to 255 for -50 to 50 m/s, 10 m above the ground. Rows run from 90 N down to 90 S, columns from 0 E eastward, one
  degree apart.
- `wind/meta.json`: the run (`run`, `valid`), the grid (`w`, `h`, `lat0`, `lon0`, `step`) and the scale (`min`, `max`).

