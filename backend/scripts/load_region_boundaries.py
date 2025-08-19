"""Load region boundaries into the generic region_boundaries table.

Currently supports NYC NTA polygons from NYC Open Data, and can be
extended via cities.yaml with --city flag.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional

import geopandas as gpd  # type: ignore
import yaml  # type: ignore
from sqlalchemy import create_engine, text

# Make sure 'backend' is on sys.path so `app` can be imported when run directly
sys.path.insert(0, str(Path(__file__).parent.parent))
from app.core.config import settings


def _load_city_config(city: str) -> Dict[str, Any]:
    cfg_path = Path(__file__).parent / "cities.yaml"
    if not cfg_path.exists():
        raise RuntimeError(f"City configuration file not found: {cfg_path}")
    with cfg_path.open("r") as f:
        data = yaml.safe_load(f) or {}
    cities = data.get("cities") or {}
    if city not in cities:
        raise RuntimeError(f"City '{city}' not found in config")
    return cities[city]


def _read_geojson_any(urls: list[str], local_path: Optional[str] = None, force_refresh: bool = False) -> "gpd.GeoDataFrame":  # type: ignore
    last_error = None
    cache_file = Path(__file__).parent / "data" / "nyc_boundaries.geojson"

    # Check for cached NYC boundaries first (unless force_refresh is True)
    if cache_file.exists() and not local_path and not force_refresh:
        try:
            # Check cache age and warn if old (but still use it)
            import datetime

            cache_age = datetime.datetime.now() - datetime.datetime.fromtimestamp(cache_file.stat().st_mtime)
            if cache_age.days > 365:
                print(f"⚠️  Cache is {cache_age.days} days old. Consider refreshing with --force-refresh")

            print(f"Using cached NYC boundaries from {cache_file}")
            gdf = gpd.read_file(cache_file)
            if gdf is not None and len(gdf) > 0:
                return gdf
        except Exception as e:
            print(f"Warning: Failed to load cached boundaries: {e}")

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

    # Try downloading from URLs
    successful_gdf = None
    for url in urls:
        try:
            print(f"Downloading region boundaries… ({url})")
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
                successful_gdf = gdf
                break
        except Exception as e:
            last_error = e
            continue

    if successful_gdf is None:
        raise RuntimeError(f"Failed to download GeoJSON from all sources. Last error: {last_error}")

    # Save to cache for future use
    try:
        cache_file.parent.mkdir(exist_ok=True)
        print(f"💾 Saving to cache: {cache_file}")
        successful_gdf.to_file(cache_file, driver="GeoJSON")
        print(f"✅ Cache created successfully with {len(successful_gdf)} regions")
    except Exception as e:
        print(f"⚠️  Warning: Failed to save cache: {e}")

    return successful_gdf


def _normalize_columns(gdf: "gpd.GeoDataFrame", fields_cfg: Dict[str, Any]) -> "gpd.GeoDataFrame":  # type: ignore
    # Accept columns according to configured name lists
    def col(names: list[str]) -> Optional[str]:
        for n in names:
            if n in gdf.columns:
                return n
        return None

    code_col = col(fields_cfg.get("code", []))
    name_col = col(fields_cfg.get("name", []))
    parent_col = col(fields_cfg.get("parent", []))
    boro_code_col = col(fields_cfg.get("boro_code", []))
    cdta_col = col(fields_cfg.get("community_district", []))

    # Fill missing expected columns with None values
    for needed, src in {
        "region_code": code_col,
        "region_name": name_col,
        "parent_region": parent_col,
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


def load_city(
    city: str, source_url: Optional[str] = None, local_path: Optional[str] = None, force_refresh: bool = False
) -> int:
    cfg = _load_city_config(city)
    sources: list[str] = [source_url] if source_url else (cfg.get("sources") or [])
    gdf = _read_geojson_any(sources, local_path, force_refresh=force_refresh)

    print("Transforming to region_boundaries schema…")
    gdf = _normalize_columns(gdf, cfg.get("fields") or {})
    out = gpd.GeoDataFrame(
        {
            "id": None,  # filled below
            "region_type": cfg.get("region_type", city),
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
        tol = float(cfg.get("simplify_tolerance", 0.0005))
        out["boundary"] = out.geometry.simplify(tol, preserve_topology=True)
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
                (:id, :rtype, :rcode, :rname, :parent,
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
                    "rtype": row.get("region_type") or cfg.get("region_type", city),
                    "rcode": (row.get("region_code") if isinstance(row.get("region_code"), (str, int)) else None),
                    "rname": row.get("region_name"),
                    "parent": row.get("parent_region"),
                    "geom": json.dumps(geom),
                    "meta": json.dumps(row.get("region_metadata") or {}),
                },
            )
            inserted += 1
    print(f"Loaded {inserted} {city.upper()} regions into region_boundaries.")
    return inserted


if __name__ == "__main__":
    try:
        parser = argparse.ArgumentParser(description="Load region boundaries for a city")
        parser.add_argument("--city", default="nyc", help="City key from cities.yaml (default: nyc)")
        parser.add_argument("--url", default=None, help="Override source URL")
        parser.add_argument("--path", default=None, help="Load from local file path instead of URL")
        parser.add_argument(
            "--force-refresh", action="store_true", help="Force download from source even if cache exists"
        )
        args = parser.parse_args()

        count = load_city(args.city, source_url=args.url, local_path=args.path, force_refresh=args.force_refresh)
        print(f"Success: {count} regions loaded for {args.city}")
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
