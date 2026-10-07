"""Run quality checks on a parcel dataset and write a QA report (CSV).

Checks:
  1. CRS present and as expected
  2. Empty / missing geometry
  3. Invalid geometry (e.g. self-intersections)
  4. Duplicate plot numbers
  5. Missing owner
  6. Declared area vs. geometry area mismatch
  7. Overlapping parcels

Usage:
  python validate_parcels.py
  python validate_parcels.py --input data/parcels.gpkg --crs EPSG:32643 --tolerance 5
"""
import argparse
import os

import geopandas as gpd
import pandas as pd
from shapely.validation import explain_validity

OVERLAP_TOLERANCE_M2 = 1.0  # ignore tiny slivers smaller than this


def validate(path, expected_crs, area_tol_pct):
    gdf = gpd.read_file(path)
    issues = []

    def add(plot_no, check, detail):
        issues.append({"plot_no": plot_no, "check": check, "detail": detail})

    # 1. CRS
    if gdf.crs is None:
        add("ALL", "CRS", "No coordinate reference system defined")
    elif gdf.crs != expected_crs:
        add("ALL", "CRS", f"CRS is {gdf.crs.to_string()}, expected {expected_crs}")

    # 2. Empty or missing geometry
    for _, row in gdf[gdf.geometry.isna() | gdf.geometry.is_empty].iterrows():
        add(row.get("plot_no"), "Missing geometry", "Geometry is empty or null")
    gdf = gdf[~(gdf.geometry.isna() | gdf.geometry.is_empty)].copy()

    # 3. Invalid geometry
    for _, row in gdf[~gdf.geometry.is_valid].iterrows():
        add(row.get("plot_no"), "Invalid geometry", explain_validity(row.geometry))

    # 4. Duplicate plot numbers
    dup = gdf[gdf["plot_no"].duplicated(keep=False)]
    for plot_no in sorted(dup["plot_no"].unique()):
        count = int((dup["plot_no"] == plot_no).sum())
        add(plot_no, "Duplicate plot number", f"Appears {count} times")

    # 5. Missing owner
    owner_missing = gdf["owner"].isna() | (gdf["owner"].astype(str).str.strip() == "")
    for _, row in gdf[owner_missing].iterrows():
        add(row["plot_no"], "Missing owner", "Owner field is blank")

    # 6. Declared area vs geometry area (valid geometries only)
    valid = gdf[gdf.geometry.is_valid].copy()
    if "declared_area_m2" in valid.columns:
        for _, row in valid.iterrows():
            declared = row["declared_area_m2"]
            if pd.isna(declared) or declared == 0:
                continue
            actual = row.geometry.area
            diff_pct = abs(actual - declared) / declared * 100
            if diff_pct > area_tol_pct:
                add(row["plot_no"], "Area mismatch",
                    f"Declared {declared:.1f} m2 vs mapped {actual:.1f} m2 ({diff_pct:.1f}% difference)")

    # 7. Overlapping parcels
    valid = valid.reset_index(drop=True)
    left, right = valid.sindex.query(valid.geometry, predicate="intersects")
    for i, j in zip(left, right):
        if i < j:
            overlap_area = valid.geometry.iloc[i].intersection(valid.geometry.iloc[j]).area
            if overlap_area > OVERLAP_TOLERANCE_M2:
                add(valid.loc[i, "plot_no"], "Overlap",
                    f"Overlaps {valid.loc[j, 'plot_no']} by {overlap_area:.1f} m2")

    return pd.DataFrame(issues, columns=["plot_no", "check", "detail"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Parcel data QA checks")
    parser.add_argument("--input", default="data/parcels.gpkg")
    parser.add_argument("--crs", default="EPSG:32643", help="Expected CRS")
    parser.add_argument("--tolerance", type=float, default=5.0,
                        help="Allowed %% difference between declared and mapped area")
    parser.add_argument("--output", default="outputs/qa_report.csv")
    args = parser.parse_args()

    report = validate(args.input, args.crs, args.tolerance)
    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    report.to_csv(args.output, index=False)

    print(f"QA report saved to {args.output}")
    if report.empty:
        print("No issues found.")
    else:
        print(f"{len(report)} issue(s) found:")
        print(report.groupby("check").size().to_string())
