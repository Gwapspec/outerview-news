# places/: the supply map seed

The supply map of [OuterView](https://outerview.world) (docs/HUB.md part 1 in the app repo): for every city of
150,000 people or more, the strongest 440 places across twelve shelves (eat, drink, see and do, shop, stay, fitness,
beauty, health, learn, get around, services, civic), from [Overture Maps](https://overturemaps.org) Places.

Every six hours the `places` workflow takes the next 40 cities from `queue.json`, streams each city's bounding box
through `overture.py` (confidence 0.6 and up, scored by confidence and distance from the centre), and commits
`places/data/<cc>_<name>.jsonl` plus `places/data/index.json` on `main`. The site imports a city's file the first
time anyone opens its page (`/city/<cc>/<name>/here`), so the job needs no secret. The first 204 cities were seeded
by hand on 2026-11-06 and are in the site's database already.

Data: Overture Maps Foundation; sources Meta, Microsoft, Foursquare (Apache-2.0, Copyright 2024 Foursquare Labs,
Inc.) and others; CDLA-Permissive-2.0 unless noted in each row's `source`. Use it with that attribution.
