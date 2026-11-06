"""The supply map seed (docs/HUB.md part 1): the strongest places per shelf for one city, from Overture Maps Places.

Reads Overture place features (geojsonseq) on stdin, writes JSON lines (one per kept place) on stdout and a summary
on stderr. Run per city, streaming, so nothing big touches the disk:

  uvx overturemaps download --bbox=W,S,E,N -f geojsonseq --type=place | python3 -I jobs/places/overture.py <cityId> <lat> <lng>

Shelves are ours and match the claim categories in web/functions/api/business.ts (eat, drink, stay, beauty, shop,
fitness, culture, health, services) plus learn, move and civic. Overture's top-level category decides the shelf, the
primary category refines it (a bar is `drink`, a salon is `beauty`). Score = confidence, minus 0.015 per km from the
city centre, plus a little for a website or a phone, so the centre and the real businesses come first.
Licence: CDLA-Permissive-2.0 (Meta, Microsoft and others), Apache-2.0 (Foursquare), CC0 (AllThePlaces); attribution on the pages.
"""
import json
import math
import sys

CAPS = {"eat": 60, "drink": 40, "shop": 50, "culture": 50, "stay": 40, "fitness": 30, "beauty": 30, "health": 30, "services": 30, "learn": 30, "move": 30, "civic": 20}
TOP = {
    "food_and_drink": "eat", "restaurant": "eat", "cafe": "drink", "casual_eatery": "eat", "food_service": "eat",
    "lodging": "stay", "shopping": "shop", "market": "shop",
    "arts_and_entertainment": "culture", "cultural_and_historic": "culture", "nightlife_venue": "drink", "stadium_arena": "culture", "memorial_site": "culture",
    "sports_and_recreation": "fitness", "sport_or_fitness_facility": "fitness", "sport_field": "fitness", "sport_league": "fitness",
    "health_care": "health", "surgery": "health", "behavioral_or_mental_health_clinic": "health",
    "lifestyle_services": "beauty", "services_and_business": "services", "education": "learn",
    "travel_and_transportation": "move", "fueling_station": "move",
    "community_and_government": "civic", "government_department": "civic", "public_safety_service": "civic", "religious_organization": "civic", "military_base": "civic",
}
DRINK = ("bar", "pub", "cafe", "coffee", "nightlife", "brewery", "wine", "tea_room", "lounge", "night_club", "beer")
BEAUTY = ("salon", "spa", "beauty", "barber", "nail", "massage", "tattoo", "wellness", "hair", "cosmetic", "skin")
MIN_CONF = 0.6


def shelf_of(top, sub):
    s = TOP.get(top)
    if s == "eat" and any(w in sub for w in DRINK):
        return "drink"
    if s == "beauty" and not any(w in sub for w in BEAUTY):
        return "services"
    return s


def km(lat1, lng1, lat2, lng2):
    p = math.pi / 180
    a = 0.5 - math.cos((lat2 - lat1) * p) / 2 + math.cos(lat1 * p) * math.cos(lat2 * p) * (1 - math.cos((lng2 - lng1) * p)) / 2
    return 12742 * math.asin(math.sqrt(a))


def main():
    city, clat, clng = sys.argv[1], float(sys.argv[2]), float(sys.argv[3])
    buckets = {}
    seen = 0
    for line in sys.stdin:
        try:
            f = json.loads(line)
        except ValueError:
            continue
        seen += 1
        p = f.get("properties") or {}
        conf = p.get("confidence") or 0
        name = ((p.get("names") or {}).get("primary") or "").strip()
        if conf < MIN_CONF or not name or len(name) > 90:
            continue
        tax = p.get("taxonomy") or {}
        hier = tax.get("hierarchy") or []
        top = hier[0] if hier else (p.get("basic_category") or "")
        sub = tax.get("primary") or p.get("basic_category") or top
        shelf = shelf_of(top, sub)
        if not shelf:
            continue
        coords = (f.get("geometry") or {}).get("coordinates") or [None, None]
        lng, lat = coords[0], coords[1]
        if lat is None or lng is None:
            continue
        addr = (p.get("addresses") or [{}])[0] or {}
        web = (p.get("websites") or [None])[0]
        phone = (p.get("phones") or [None])[0]
        brand = ((p.get("brand") or {}).get("names") or {}).get("primary")
        src = ((p.get("sources") or [{}])[0] or {}).get("dataset") or ""
        d = km(clat, clng, lat, lng)
        score = conf - 0.015 * d + (0.05 if web else 0) + (0.02 if phone else 0)
        row = {"id": f.get("id"), "place": city, "name": name, "shelf": shelf, "sub": sub, "lat": round(lat, 5), "lng": round(lng, 5), "addr": addr.get("freeform"), "locality": addr.get("locality"), "website": web, "phone": phone, "brand": brand, "conf": round(conf, 3), "score": round(score, 4), "source": src}
        buckets.setdefault(shelf, []).append(row)
    kept = 0
    for shelf, rows in buckets.items():
        rows.sort(key=lambda r: r["score"], reverse=True)
        for r in rows[: CAPS[shelf]]:
            print(json.dumps(r, ensure_ascii=False))
            kept += 1
    print(json.dumps({"city": city, "seen": seen, "shelves": {k: len(v) for k, v in buckets.items()}, "kept": kept}), file=sys.stderr)


if __name__ == "__main__":
    main()
