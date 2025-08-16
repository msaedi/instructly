"""Load region boundaries into the generic region_boundaries table.

Currently supports NYC NTA polygons from NYC Open Data.
"""

import sys

import geopandas as gpd  # type: ignore
from sqlalchemy import create_engine

from app.core.config import settings


def load_nyc_neighborhoods() -> int:
    url = "https://data.cityofnewyork.us/api/geospatial/cpf4-rkhq?method=export&format=GeoJSON"
    print("Downloading NYC NTA GeoJSON…")
    gdf = gpd.read_file(url)

    # Normalize expected columns
    required = ["ntacode", "ntaname", "boroname", "borocode", "cdta", "geometry"]
    for col in required:
        if col not in gdf.columns:
            gdf[col] = None

    print("Transforming to region_boundaries schema…")
    out = gpd.GeoDataFrame(
        {
            "region_type": "nyc",
            "region_code": gdf["ntacode"],
            "region_name": gdf["ntaname"],
            "parent_region": gdf["boroname"],
            "boundary": gdf.geometry,
            "region_metadata": gdf.apply(
                lambda r: {
                    "borough_code": r.get("borocode"),
                    "community_district": r.get("cdta"),
                },
                axis=1,
            ),
        },
        geometry="boundary",
        crs=gdf.crs,
    )

    # Reproject to EPSG:4326 if needed
    if out.crs is None or out.crs.to_epsg() != 4326:
        out = out.to_crs(epsg=4326)

    engine = create_engine(settings.database_url)
    print("Writing to region_boundaries table…")
    out.to_postgis("region_boundaries", engine, if_exists="append", index=False)
    print(f"Loaded {len(out)} NYC regions into region_boundaries.")
    return len(out)


if __name__ == "__main__":
    try:
        count = load_nyc_neighborhoods()
        print(f"Success: {count} regions loaded")
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
