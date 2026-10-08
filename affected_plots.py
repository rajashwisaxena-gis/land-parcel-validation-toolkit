"""Identify parcels affected by a linear scheme and produce:
  - an Excel schedule similar to a Book of Reference
  - a simple Land Plan style map (PNG)

Method: buffer the alignment by a corridor width, intersect with parcels,
and report each affected plot with its total and affected area.

Usage:
  python affected_plots.py
  python affected_plots.py --buffer 25 --parcels data/parcels.gpkg --alignment data/alignment.gpkg
"""
import argparse
import os

import geopandas as gpd
import matplotlib

matplotlib.use("Agg")  # no display needed, saves straight to file
import matplotlib.pyplot as plt
import pandas as pd

MIN_AFFECTED_M2 = 0.5  # ignore touching/edge-only intersections


def find_affected(parcels_path, alignment_path, buffer_m):
    parcels = gpd.read_file(parcels_path)
    alignment = gpd.read_file(alignment_path)

    if alignment.crs != parcels.crs:
        alignment = alignment.to_crs(parcels.crs)

    # Skip invalid or empty geometries (run validate_parcels.py to see them)
    bad = parcels.geometry.isna() | parcels.geometry.is_empty | ~parcels.geometry.is_valid
    if bad.any():
        print(f"Warning: skipping {int(bad.sum())} invalid/empty parcel(s). "
              "Run validate_parcels.py for details.")
    parcels = parcels[~bad].copy()

    buffered = alignment.buffer(buffer_m)
    corridor = buffered.union_all() if hasattr(buffered, "union_all") else buffered.unary_union

    parcels["affected_area_m2"] = parcels.geometry.intersection(corridor).area
    parcels["total_area_m2"] = parcels.geometry.area
    affected = parcels[parcels["affected_area_m2"] > MIN_AFFECTED_M2].copy()
    affected["affected_pct"] = affected["affected_area_m2"] / affected["total_area_m2"] * 100
    affected = affected.sort_values("plot_no").reset_index(drop=True)
    return parcels, affected, corridor, alignment


def write_schedule(affected, out_path):
    owner = affected["owner"].fillna("UNKNOWN - to be traced")
    occupier = affected["occupier"].fillna("UNKNOWN - to be traced") if "occupier" in affected else ""
    schedule = pd.DataFrame({
        "Ref No": range(1, len(affected) + 1),
        "Plot No": affected["plot_no"],
        "Owner": owner,
        "Occupier": occupier,
        "Total area (m2)": affected["total_area_m2"].round(1),
        "Affected area (m2)": affected["affected_area_m2"].round(1),
        "Affected (%)": affected["affected_pct"].round(1),
        "Take": affected["affected_pct"].apply(lambda p: "Whole" if p >= 99 else "Part"),
    })
    with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
        schedule.to_excel(writer, sheet_name="Schedule", index=False)
        ws = writer.sheets["Schedule"]
        for col in ws.columns:  # simple column auto-width
            width = max(len(str(cell.value)) if cell.value is not None else 0 for cell in col)
            ws.column_dimensions[col[0].column_letter].width = width + 3
    return schedule


def draw_plan(parcels, affected, corridor, alignment, out_path):
    fig, ax = plt.subplots(figsize=(11, 7))
    parcels.plot(ax=ax, facecolor="#f2f2f2", edgecolor="#999999", linewidth=0.6)
    affected.plot(ax=ax, facecolor="#f4a261", edgecolor="#7a3e00", linewidth=0.9, alpha=0.8)
    gpd.GeoSeries([corridor], crs=parcels.crs).boundary.plot(
        ax=ax, color="#d00000", linewidth=1.2, linestyle="--")
    alignment.plot(ax=ax, color="#1d3557", linewidth=2)

    for _, row in affected.iterrows():
        point = row.geometry.representative_point()
        ax.annotate(row["plot_no"], (point.x, point.y), ha="center", fontsize=7)

    ax.set_title("Land Plan (sample data) - affected plots along alignment", fontsize=12)
    ax.set_xlabel("Easting (m)")
    ax.set_ylabel("Northing (m)")
    ax.set_aspect("equal")
    ax.annotate("N", xy=(0.97, 0.95), xycoords="axes fraction", fontsize=14, ha="center")
    ax.annotate("", xy=(0.97, 0.94), xytext=(0.97, 0.88), xycoords="axes fraction",
                arrowprops=dict(arrowstyle="-|>", color="black"))
    ax.legend(handles=[
        plt.Rectangle((0, 0), 1, 1, fc="#f2f2f2", ec="#999999", label="Parcel"),
        plt.Rectangle((0, 0), 1, 1, fc="#f4a261", ec="#7a3e00", label="Affected parcel"),
        plt.Line2D([0], [0], color="#1d3557", lw=2, label="Alignment"),
        plt.Line2D([0], [0], color="#d00000", lw=1.2, ls="--", label="Corridor limit"),
    ], loc="lower right", fontsize=8)
    fig.tight_layout()
    fig.savefig(out_path, dpi=200)
    plt.close(fig)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Affected plot identification")
    parser.add_argument("--parcels", default="data/parcels.gpkg")
    parser.add_argument("--alignment", default="data/alignment.gpkg")
    parser.add_argument("--buffer", type=float, default=20.0,
                        help="Corridor half-width in metres (each side of alignment)")
    parser.add_argument("--outdir", default="outputs")
    args = parser.parse_args()

    os.makedirs(args.outdir, exist_ok=True)
    parcels, affected, corridor, alignment = find_affected(
        args.parcels, args.alignment, args.buffer)

    schedule = write_schedule(affected, os.path.join(args.outdir, "book_of_reference.xlsx"))
    draw_plan(parcels, affected, corridor, alignment, os.path.join(args.outdir, "land_plan.png"))

    print(f"{len(affected)} affected plot(s) within {args.buffer} m of the alignment")
    print(f"Saved: {args.outdir}/book_of_reference.xlsx and {args.outdir}/land_plan.png")
