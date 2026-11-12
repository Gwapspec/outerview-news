# OuterView news tiles

Built every 15 minutes from the GDELT Project's GKG files by the workflow in the `main` branch of this
repository. One JSON file per 10-degree tile, the last 24 hours of stories, headline and link only. Data: GDELT
Project (cite GDELT). Used by https://outerview.world.

`tiles/money.json` and `tiles/politics.json` hold the last 24 hours of money news and politics news for the whole
world, chosen by GDELT's topic marks (the rules are in the `main` branch's README). Nobody picks the stories.

A story several outlets carried is one row that lists them: `ds` the outlets, `us` each one's own link, `dc` the
country each is based in. The countries come from the GDELT Project's list of news outlets by country (May 2018);
they are GDELT's estimate and can be wrong, and an outlet that is not on the list has none.

`tiles/country/<cc>.json` is one country's news at home in the last 24 hours (`cc` is GDELT's FIPS country code): `top`
its stories (those an outlet based there carries first, then the most carried), `politics` and `money` its rows of the two topic files. A story is a country's own when
its first city is there and it names that country most. `tiles/country/index.json` counts each country's stories
by language.
