"""`overturemaps download` with the release pinned, so nothing calls the STAC catalog (stac.overturemaps.org answers
429 Too Many Requests to GitHub's runners, which killed whole seed runs). Same arguments and output as the CLI.
usage: python3 -I places/download.py --bbox=W,S,E,N -f geojsonseq --type=place"""
import sys

import overturemaps.core as core

RELEASE = "2026-10-21.0"  # bump when a newer release is worth a full reseed
core._cached_stac_catalog = {"latest": RELEASE, "links": [{"rel": "child", "href": f"./{RELEASE}/catalog.json"}]}

from overturemaps.cli import cli  # noqa: E402  (after the cache is primed)

sys.argv = ["overturemaps", "download", "--release", RELEASE, "--no-stac", *sys.argv[1:]]
cli()
