"""Generate SYNTHETIC parcel and alignment data for demonstration.

No real land records are used. The parcels form a simple grid, and a few
deliberate errors are planted so the validation script has something to find.

Run:  python make_sample_data.py
Creates: data/parcels.gpkg and data/alignment.gpkg
"""
import os

import geopandas as gpd
from shapely.geometry import LineString, Polygon, box

CRS = "EPSG:32643"  # WGS 84 / UTM zone 43N (metres), suitable for the Delhi region
X0, Y0 = 700000, 3170000  # arbitrary origin of the sample grid
WIDTH, HEIGHT = 100, 80  # parcel size in metres
ROWS, COLS = 5, 8

OWNERS = [
    "A. Sharma", "R. Verma", "S. Gupta", "M. Khan", "P. Singh",
    "N. Mehta", "K. Joshi", "D. Rao", "L. Iyer", "T. Das",
]
OCCUPIERS = ["Owner occupied", "Tenant - J. Roy", "Tenant - F. Ali", "Vacant"]


def build_parcels():
    records = []
    n = 1
    for r in range(ROWS):
        for c in range(COLS):
            geom = box(
                X0 + c * WIDTH, Y0 + r * HEIGHT,
                X0 + (c + 1) * WIDTH, Y0 + (r + 1) * HEIGHT,
            )
            records.append({
                "plot_no": f"P{n:03d}",
                "owner": OWNERS[n % len(OWNERS)],
                "occupier": OCCUPIERS[n % len(OCCUPIERS)],
                "declared_area_m2": round(geom.area, 1),
                "geometry": geom,
            })
            n += 1

    # ---- Deliberate errors (so the QA script has something to catch) ----
    records[4]["owner"] = None                          # missing owner
    records[9]["plot_no"] = records[8]["plot_no"]       # duplicate plot number
    records[14]["declared_area_m2"] = 5000.0            # area mismatch
    # invalid "bowtie" polygon (self-intersecting)
    bx, by = X0 + 4 * WIDTH, Y0 + 2 * HEIGHT
    records[20]["geometry"] = Polygon([
        (bx, by), (bx + WIDTH, by + HEIGHT),
        (bx + WIDTH, by), (bx, by + HEIGHT),
    ])
    # an extra parcel that overlaps an existing one
    ox, oy = X0 + 6 * WIDTH + 30, Y0 + 3 * HEIGHT + 20
    overlap = box(ox, oy, ox + WIDTH, oy + HEIGHT)
    records.append({
        "plot_no": "P041", "owner": "V. Nair", "occupier": "Vacant",
        "declared_area_m2": round(overlap.area, 1), "geometry": overlap,
    })

    return gpd.GeoDataFrame(records, geometry="geometry", crs=CRS)


def build_alignment():
    """A sample linear scheme (e.g. a road or pipeline) crossing the grid."""
    line = LineString([
        (X0 - 50, Y0 + 60),
        (X0 + 300, Y0 + 150),
        (X0 + 550, Y0 + 260),
        (X0 + 850, Y0 + 340),
    ])
    return gpd.GeoDataFrame({"name": ["Sample alignment"]}, geometry=[line], crs=CRS)


if __name__ == "__main__":
    os.makedirs("data", exist_ok=True)
    build_parcels().to_file("data/parcels.gpkg", driver="GPKG")
    build_alignment().to_file("data/alignment.gpkg", driver="GPKG")
    print("Created data/parcels.gpkg and data/alignment.gpkg (synthetic data)")
