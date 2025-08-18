"""Load region boundaries into the generic region_boundaries table.

Currently supports NYC NTA polygons from NYC Open Data.
"""

import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional

import geopandas as gpd  # type: ignore
from sqlalchemy import create_engine, text

# Make sure 'backend' is on sys.path so `app` can be imported when run directly
sys.path.insert(0, str(Path(__file__).parent.parent))
from app.core.config import settings


def _candidate_urls() -> list[str]:
    # Try multiple sources; the first valid one will be used
    return [
        # NYC 2020 NTAs (Socrata) – JSON list with the_geom
        "https://data.cityofnewyork.us/resource/9nt8-h7nd.geojson",
        "https://data.cityofnewyork.us/resource/9nt8-h7nd.json",
        # NYC Open Data NTA export (commonly used ID)
        "https://data.cityofnewyork.us/api/geospatial/7t3b-ywvw?method=export&format=GeoJSON",
        # Alternate ID (older references)
        "https://data.cityofnewyork.us/api/geospatial/cpf4-rkhq?method=export&format=GeoJSON",
        # NYC Planning Labs mirror
        "https://raw.githubusercontent.com/NYCPlanning/labs-nyc-boundaries/master/data/geojson/ntas.geojson",
        # Socrata resource endpoint (returns rows with geometry field)
        "https://data.cityofnewyork.us/resource/7t3b-ywvw.geojson?$limit=100000",
        "https://data.cityofnewyork.us/resource/cpf4-rkhq.geojson?$limit=100000",
    ]


def _read_geojson_any(url: Optional[str] = None, local_path: Optional[str] = None) -> "gpd.GeoDataFrame":  # type: ignore
    last_error = None
    # Prefer local file if provided
    if local_path:
        p = Path(local_path)
        if not p.exists():
            raise RuntimeError(f"Local path not found: {local_path}")
        print(f"Loading GeoJSON/Shapefile from local path: {p}")
        gdf = gpd.read_file(p)
        if gdf is None or len(gdf) == 0:
            raise RuntimeError("Local file loaded but contains no features")
        return gdf

    urls = [url] if url else _candidate_urls()
    for url in urls:
        try:
            print(f"Downloading NYC NTA GeoJSON… ({url})")
            # Handle Socrata JSON list shape when not GeoJSON FeatureCollection
            if url.endswith(".json") and not url.endswith(".geojson"):
                import pandas as pd  # type: ignore
                import requests
                from shapely.geometry import shape  # type: ignore

                r = requests.get(url, timeout=60)
                r.raise_for_status()
                rows = r.json()
                if not isinstance(rows, list) or not rows:
                    raise RuntimeError("Unexpected JSON format (expected list)")
                geometries = []
                for rec in rows:
                    geom = rec.get("the_geom") or rec.get("geometry")
                    if not geom:
                        continue
                    geometries.append(shape(geom))
                df = pd.DataFrame(rows)
                if not geometries:
                    raise RuntimeError("No geometries in JSON rows")
                gdf = gpd.GeoDataFrame(df, geometry=geometries, crs="EPSG:4326")
            else:
                gdf = gpd.read_file(url)
            if gdf is not None and len(gdf) > 0:
                return gdf
        except Exception as e:
            last_error = e
            continue
    raise RuntimeError(f"Failed to download NTA GeoJSON from all sources. Last error: {last_error}")


def _normalize_nyc_columns(gdf: "gpd.GeoDataFrame") -> "gpd.GeoDataFrame":  # type: ignore
    # Accept both uppercase/lowercase variants from different sources
    def col(*names: str) -> Optional[str]:
        for n in names:
            if n in gdf.columns:
                return n
        return None

    code_col = col("ntacode", "NTACode", "nta_code", "nta2020")
    name_col = col("ntaname", "NTAName", "nta_name", "name", "Name")
    boro_col = col("boroname", "BoroName", "borough", "Borough")
    boro_code_col = col("borocode", "BoroCode")
    cdta_col = col("cdta", "CDTA", "cdta2020")

    # Fill missing expected columns with None values
    for needed, src in {
        "region_code": code_col,
        "region_name": name_col,
        "parent_region": boro_col,
    }.items():
        if src is None:
            gdf[needed] = None
        else:
            gdf[needed] = gdf[src]

    # Build metadata
    gdf["region_metadata"] = gdf.apply(
        lambda r: {
            "borough_code": (r.get(boro_code_col) if boro_code_col else None),
            "community_district": (r.get(cdta_col) if cdta_col else None),
        },
        axis=1,
    )
    return gdf


def _add_ulids(df):
    try:
        import ulid  # type: ignore

        df["id"] = [str(ulid.ULID()) for _ in range(len(df))]
    except Exception:
        import uuid

        df["id"] = [uuid.uuid4().hex[:26] for _ in range(len(df))]
    return df


def load_nyc_neighborhoods(source_url: Optional[str] = None, local_path: Optional[str] = None) -> int:
    gdf = _read_geojson_any(source_url, local_path)

    print("Transforming to region_boundaries schema…")
    gdf = _normalize_nyc_columns(gdf)
    out = gpd.GeoDataFrame(
        {
            "id": None,  # filled below
            "region_type": "nyc",
            "region_code": gdf["region_code"],
            "region_name": gdf["region_name"],
            "parent_region": gdf["parent_region"],
            "boundary": gdf.geometry,
            "region_metadata": gdf["region_metadata"],
        },
        geometry="boundary",
        crs=gdf.crs,
    )

    # Reproject to EPSG:4326 if needed
    if out.crs is None or out.crs.to_epsg() != 4326:
        out = out.to_crs(epsg=4326)

    # Simplify geometry for web use while keeping original shape adequate
    try:
        out["boundary"] = out.geometry.simplify(0.0005, preserve_topology=True)
    except Exception:
        pass

    out = _add_ulids(out)
    engine = create_engine(settings.database_url)
    print("Writing to region_boundaries table…")
    # Avoid to_postgis JSON typing issues; write with explicit INSERTs
    inserted = 0
    with engine.begin() as conn:
        sql = text(
            """
            INSERT INTO region_boundaries
                (id, region_type, region_code, region_name, parent_region, boundary, centroid, region_metadata, created_at, updated_at)
            VALUES
                (:id, 'nyc', :rcode, :rname, :parent,
                 ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(:geom), 4326)),
                 ST_Centroid(ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(:geom), 4326))),
                 CAST(:meta AS JSONB), NOW(), NOW())
            ON CONFLICT (id) DO NOTHING
            """
        )
        for _, row in out.iterrows():
            # Access the actual geometry column by name ('boundary') to avoid Series.geometry error
            geom_obj = row["boundary"] if "boundary" in row else None
            geom = getattr(geom_obj, "__geo_interface__", None)
            if not geom:
                continue
            conn.execute(
                sql,
                {
                    "id": row["id"],
                    "rcode": (row.get("region_code") if isinstance(row.get("region_code"), (str, int)) else None),
                    "rname": row.get("region_name"),
                    "parent": row.get("parent_region"),
                    "geom": json.dumps(geom),
                    "meta": json.dumps(row.get("region_metadata") or {}),
                },
            )
            inserted += 1
    print(f"Loaded {inserted} NYC regions into region_boundaries.")
    return inserted


if __name__ == "__main__":
    try:
        # Optional CLI args: --url=<geojson_url> or --path=/absolute/or/relative/path
        arg_url: Optional[str] = None
        arg_path: Optional[str] = None
        for a in sys.argv[1:]:
            if a.startswith("--url="):
                arg_url = a.split("=", 1)[1].strip()
            if a.startswith("--path="):
                arg_path = a.split("=", 1)[1].strip()
        count = load_nyc_neighborhoods(source_url=arg_url, local_path=arg_path)
        print(f"Success: {count} regions loaded")
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
