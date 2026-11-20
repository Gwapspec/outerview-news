# Opening hours for OuterView's places

Once a week, OpenStreetMap's `opening_hours` matched to the places on [OuterView](https://outerview.world)'s Boards and
worked out for the next 14 days. Made by `places/hours.py` on the `main` branch (the method of matching, published as
the Open Database License asks).

**Data © [OpenStreetMap contributors](https://www.openstreetmap.org/copyright), available under the
[Open Database License 1.0](https://opendatacommons.org/licenses/odbl/1-0/).** These files are a derivative database of
OpenStreetMap and are offered under the same licence. Place ids are [Overture Maps](https://overturemaps.org) ids.

- **Source:** OpenStreetMap US's [Layercake](https://layercake.openstreetmap.us/layers/pois/) `pois.parquet`, the named
  places with `opening_hours`.
- **Match:** a place on OuterView and an OpenStreetMap object with the same name (accents and case folded; one name may
  be the other with a word more, if at least two thirds as long) within 80 metres; the nearest wins, one to one.
- **Hours:** the [opening-hours](https://github.com/remi-dupre/opening-hours-rs) parser (MIT or Apache-2.0), with the
  time zone and public holidays of the place's coordinates.

`<cc>_<name>.json`: `{ place, made, rows: [{ id, osm, d, o, n?, wd? }] }`. `id` is the Overture id, `osm` the
OpenStreetMap object (`n` node, `w` way, `r` relation, then its number), `d` the place's local date the window starts,
`o` the open stretches as start and end minutes from that date's midnight on the place's own clock (14 days: 0 to
20160), `n` a note OpenStreetMap gives with a closure, `wd` its Wikidata id. `index.json`: per city, how many places
have hours (`n`) of how many (`of`), and the run's date.
