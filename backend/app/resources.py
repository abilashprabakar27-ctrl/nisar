"""Every resource from the challenge page, tagged so the app can show the right one in the right place
(How we know, What's next, the assistant, the credits on each result)."""

NON_US_NOTICE = ("NASA does not endorse any non-U.S. Government entity and is not responsible for information on "
                 "non-U.S. Government websites. For those sources, their own data-use terms apply.")

RESOURCES = [
    # NASA data and access
    {"id": "earthdata-search", "title": "NASA Earthdata Search", "url": "https://search.earthdata.nasa.gov/search",
     "kind": "data", "used_for": "NASA OPERA water maps for the sources-agree check", "tags": ["data", "verify"]},
    {"id": "asf-vertex", "title": "ASF Data Search Vertex", "url": "https://search.asf.alaska.edu/",
     "kind": "data", "used_for": "NISAR GCOV passes (searched by the app through the ASF API)", "tags": ["data", "nisar"]},
    {"id": "nisar-guide", "title": "NISAR Data User Guide (ASF)", "url": "https://nisar-docs.asf.alaska.edu/",
     "kind": "docs", "used_for": "GCOV layers, mask, quality levels, known issues", "tags": ["method", "nisar"]},
    # Learning
    {"id": "intro-rs", "title": "Intro to Remote Sensing",
     "url": "https://www.earthdata.nasa.gov/learn/earth-observation-data-basics/remote-sensing",
     "kind": "learn", "tags": ["learn", "basics"]},
    {"id": "intro-sar", "title": "Intro to Synthetic Aperture Radar (SAR)",
     "url": "https://www.earthdata.nasa.gov/learn/earth-observation-data-basics/sar",
     "kind": "learn", "tags": ["learn", "polarization", "sar"]},
    {"id": "arset", "title": "NASA ARSET Trainings", "url": "https://appliedsciences.nasa.gov/get-involved/training",
     "kind": "learn", "tags": ["learn", "floods", "next"]},
    {"id": "storymaps", "title": "NISAR StoryMaps", "url": "https://nisar.jpl.nasa.gov/applications/arcgis-storymaps/",
     "kind": "learn", "tags": ["stories", "floods", "wildfire", "subsidence", "glaciers"]},
    {"id": "white-papers", "title": "NISAR Applications White Papers",
     "url": "https://nisar.jpl.nasa.gov/applications/societal-benefit/", "kind": "learn", "tags": ["next", "impact"]},
    {"id": "uavsar", "title": "UAVSAR Postcards", "url": "https://uavsar.jpl.nasa.gov/education/postcards.html",
     "kind": "learn", "used_for": "inspiration for the HH / HV colour mix", "tags": ["polarization", "colour"]},
    # Partner agencies (non-US: own terms apply)
    {"id": "rcm", "title": "RADARSAT Constellation Mission (RCM) - Data",
     "url": "https://donnees-data.asc-csa.gc.ca/en/dataset/rcm", "kind": "partner", "non_us": True,
     "used_for": "C-band availability check (EODMS search)", "tags": ["partner", "verify"]},
    {"id": "csa-sar-tutorial", "title": "CSA Synthetic Aperture Radar Python Tutorial",
     "url": "https://github.com/asc-csa/Synthetic_Aperture_Radar_Tutorial", "kind": "learn", "non_us": True,
     "tags": ["learn", "python", "qgis"]},
    {"id": "radarsat1", "title": "RADARSAT-1 - Data (open licence)",
     "url": "https://donnees-data.asc-csa.gc.ca/en/dataset/radarsat1", "kind": "partner", "non_us": True,
     "used_for": "long-term history availability (1995-2013)", "tags": ["partner", "history"]},
    {"id": "saocom", "title": "SAOCOM Catalogue (CONAE)",
     "url": "https://catalogos.conae.gov.ar/catalogo/catalogoSatSaocomInfo.html", "kind": "partner", "non_us": True,
     "used_for": "L-band cross-check, recorded by the team", "tags": ["partner", "verify"]},
    {"id": "saocom-registration", "title": "SAOCOM Catalogue Registration (ONE CLICK)",
     "url": "https://www.argentina.gob.ar/noticias/la-informacion-saocom-cada-vez-mas-accesible", "kind": "partner",
     "non_us": True, "tags": ["partner"]},
    # Supporting data used by the backend
    {"id": "opera", "title": "NASA OPERA DSWx-S1 surface water", "url": "https://www.earthdata.nasa.gov/data/projects/opera",
     "kind": "data", "used_for": "separate NASA water map (Sentinel-1 radar)", "tags": ["verify"]},
    {"id": "power", "title": "NASA POWER daily precipitation", "url": "https://power.larc.nasa.gov/",
     "kind": "data", "used_for": "rain evidence for Why", "tags": ["drivers"]},
    {"id": "firms", "title": "NASA FIRMS fire hotspots", "url": "https://firms.modaps.eosdis.nasa.gov/",
     "kind": "data", "used_for": "fire evidence for Why", "tags": ["drivers"]},
    {"id": "usgs", "title": "USGS earthquake catalogue", "url": "https://earthquake.usgs.gov/fdsnws/event/1/",
     "kind": "data", "used_for": "earthquake evidence for Why", "tags": ["drivers"]},
    {"id": "cop-dem", "title": "Copernicus DEM GLO-30", "url": "https://registry.opendata.aws/copernicus-dem/",
     "kind": "data", "non_us": True, "used_for": "slope mask and flat-land check", "tags": ["drivers", "method"]},
    {"id": "worldview", "title": "NASA Worldview snapshots", "url": "https://worldview.earthdata.nasa.gov/",
     "kind": "data", "used_for": "context photo", "tags": ["verify"]},
]


def by_tag(tag: str | None = None):
    items = RESOURCES if not tag else [r for r in RESOURCES if tag in r.get("tags", [])]
    return {"notice": NON_US_NOTICE, "resources": items}


def credits(used_ids: list[str]):
    idx = {r["id"]: r for r in RESOURCES}
    items = [idx[i] for i in used_ids if i in idx]
    return {"sources": [{"title": r["title"], "url": r["url"], "used_for": r.get("used_for")} for r in items],
            "notice": NON_US_NOTICE if any(r.get("non_us") for r in items) else None}
