#!/usr/bin/env python3
"""
gtfs_to_png.py
Generates a transparent PNG image 'overlay.png' from a GTFS shapes.txt file
Optional: routes.txt, trips.txt, stops.txt for colors/stops.
Usage:
    python gtfs_to_png.py --shapes shapes.txt --out overlay.png
"""
import argparse
import json
import matplotlib.pyplot as plt
import pandas as pd
import geopandas as gpd

from pathlib import Path
from shapely.geometry import LineString, Point


def read_shapes(shapes_path):
    # GTFS shapes.txt has: shape_id,shape_pt_lat,shape_pt_lon,shape_pt_sequence (and optional dist_traveled)
    df = pd.read_csv(shapes_path, dtype={"shape_id": str})
    required = {"shape_id", "shape_pt_lat", "shape_pt_lon", "shape_pt_sequence"}
    if not required.issubset(set(df.columns)):
        raise SystemExit(f"shapes.txt missing columns: {required - set(df.columns)}")
    df = df.sort_values(["shape_id", "shape_pt_sequence"])
    lines = []
    for sid, group in df.groupby("shape_id"):
        coords = list(
            zip(
                group["shape_pt_lon"].astype(float), group["shape_pt_lat"].astype(float)
            )
        )
        if len(coords) < 2:
            continue
        lines.append({"shape_id": sid, "geometry": LineString(coords)})
    gdf = gpd.GeoDataFrame(lines, crs="EPSG:4326")
    return gdf


def optionally_read_routes(routes_path):
    if routes_path is None:
        return None
    r = pd.read_csv(routes_path, dtype={"route_id": str})
    # route_color may or may not exist
    return r


def optionally_read_trips(trips_path):
    if trips_path is None:
        return None
    t = pd.read_csv(
        trips_path, dtype={"trip_id": str, "route_id": str, "shape_id": str}
    )
    return t


def optionally_read_stops(stops_path):
    if stops_path is None:
        return None
    s = pd.read_csv(stops_path, dtype={"stop_id": str})
    # require lat/lon
    if not {"stop_lat", "stop_lon"}.issubset(s.columns):
        return None
    g = gpd.GeoDataFrame(
        s,
        geometry=gpd.points_from_xy(s.stop_lon.astype(float), s.stop_lat.astype(float)),
        crs="EPSG:4326",
    )
    return g


def compute_bbox(gdf, padding_fraction=0.02):
    # returns (minx,miny,maxx,maxy) in lon/lat
    minx = gdf.total_bounds[0]
    miny = gdf.total_bounds[1]
    maxx = gdf.total_bounds[2]
    maxy = gdf.total_bounds[3]
    dx = maxx - minx
    dy = maxy - miny
    # if degenerate, expand manually
    if dx == 0:
        dx = 0.001
    if dy == 0:
        dy = 0.001
    padx = dx * padding_fraction
    pady = dy * padding_fraction
    return (minx - padx, miny - pady, maxx + padx, maxy + pady)


def plot_to_png(
    shapes_gdf,
    stops_gdf=None,
    out_png="overlay.png",
    dpi=150,
    linewidth=2.0,
    route_color_map=None,
    bbox=None,
    background_color=None,
    scale=1.0,
):
    if bbox is None:
        bbox = compute_bbox(shapes_gdf)
    minx, miny, maxx, maxy = bbox

    width_deg = maxx - minx
    height_deg = maxy - miny
    base_px = int(1200 * scale)
    aspect = height_deg / width_deg if width_deg != 0 else 1.0
    px_w = base_px
    px_h = int(base_px * aspect)

    fig_w = px_w / dpi
    fig_h = px_h / dpi

    fig, ax = plt.subplots(figsize=(fig_w, fig_h), dpi=dpi)
    ax.set_axis_off()
    ax.set_xlim(minx, maxx)
    ax.set_ylim(miny, maxy)
    # draw shapes
    # optionally allow per-shape color via shapes_gdf['color'] if present
    if "color" in shapes_gdf.columns:
        for _, row in shapes_gdf.iterrows():
            c = row["color"] if pd.notna(row["color"]) else "#000000"
            g = gpd.GeoSeries([row.geometry], crs=shapes_gdf.crs)
            g.plot(ax=ax, linewidth=linewidth, zorder=2, antialiased=True)
    else:
        shapes_gdf.plot(ax=ax, linewidth=linewidth, zorder=2, antialiased=True)

    # draw stops if available
    if stops_gdf is not None:
        stops_gdf.plot(ax=ax, markersize=6, zorder=3)

    # set transparent background
    if background_color:
        fig.patch.set_facecolor(background_color)
    else:
        fig.patch.set_alpha(0.0)
    ax.patch.set_alpha(0.0)

    # save
    fig.savefig(out_png, bbox_inches="tight", pad_inches=0, transparent=True)
    plt.close(fig)
    return bbox


def enrich_colors_from_routes(shapes_gdf, trips_df, routes_df):
    # join trips->routes->route_color for shapes where shape_id appears in trips
    if trips_df is None or routes_df is None:
        return shapes_gdf
    # ensure columns exist
    if "shape_id" not in trips_df.columns or "route_id" not in trips_df.columns:
        return shapes_gdf
    if "route_id" not in routes_df.columns:
        return shapes_gdf
    # merge
    trip_route = trips_df[["shape_id", "route_id"]].drop_duplicates()
    route_color = (
        routes_df[["route_id", "route_color"]].drop_duplicates()
        if "route_color" in routes_df.columns
        else None
    )
    if route_color is None:
        return shapes_gdf
    merged = trip_route.merge(route_color, on="route_id", how="left")
    # map shape_id -> color
    color_map = dict(merged[["shape_id", "route_color"]].dropna().values)
    shapes_gdf = shapes_gdf.copy()
    shapes_gdf["color"] = shapes_gdf["shape_id"].map(color_map)
    return shapes_gdf


def filter_shapes_by_route(shapes_gdf, trips_df, route_ids):
    """
    Filter shapes to export based on the desired route_id list.
    """
    if trips_df is None or route_ids is None:
        return shapes_gdf
    if isinstance(route_ids, str):
        route_ids = [route_ids]
    # list of shape_id associated with these route_id
    shape_ids = (
        trips_df.loc[trips_df["route_id"].isin(route_ids), "shape_id"].unique().tolist()
    )
    filtered = shapes_gdf[shapes_gdf["shape_id"].isin(shape_ids)]
    return filtered


def filter_shapes_by_route_and_direction(
    shapes_gdf, trips_df, route_ids, direction=None
):
    """
    Filter shapes to export based on route_id list and optional direction.
    """
    if trips_df is None or route_ids is None:
        return shapes_gdf
    if isinstance(route_ids, str):
        route_ids = [route_ids]
    # Filter trips by route_id
    trips_filtered = trips_df[trips_df["route_id"].isin(route_ids)]
    # Filter by direction if specified
    if direction is not None and "direction_id" in trips_filtered.columns:
        trips_filtered = trips_filtered[trips_filtered["direction_id"] == direction]
    # List of shape_ids to keep
    shape_ids = trips_filtered["shape_id"].unique().tolist()
    filtered = shapes_gdf[shapes_gdf["shape_id"].isin(shape_ids)]
    return filtered


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--shapes", required=True, help="shapes.txt")
    p.add_argument("--routes", help="routes.txt (optional, for colors)")
    p.add_argument("--trips", help="trips.txt (optional, for route_id filtering)")
    p.add_argument("--stops", help="stops.txt (optional, to draw stops)")
    p.add_argument(
        "--direction",
        type=int,
        choices=[0, 1],
        default=None,
        help="Draw only this direction (0 or 1). Default: all directions",
    )
    p.add_argument("--out", default="overlay.png", help="output PNG filename")
    p.add_argument("--dpi", type=int, default=150)
    p.add_argument("--linewidth", type=float, default=2.0)
    p.add_argument("--pad", type=float, default=0.02, help="bbox margin fraction")
    p.add_argument(
        "--scale", type=float, default=1.0, help="resolution scale (1=base, 2=HD)"
    )
    p.add_argument(
        "--color", default="#ff0000", help="Line color in hex or name (default red)"
    )
    p.add_argument("--route_id", help="Filter a single route (e.g.: 42)")
    p.add_argument(
        "--route_ids", help="Multiple routes separated by commas (e.g.: 42,44,46)"
    )
    args = p.parse_args()

    shapes_gdf = read_shapes(args.shapes)
    trips_df = (
        None
        if args.trips is None
        else pd.read_csv(args.trips, dtype={"shape_id": str, "route_id": str})
    )
    routes_df = (
        None
        if args.routes is None
        else pd.read_csv(args.routes, dtype={"route_id": str})
    )
    stops_gdf = optionally_read_stops(args.stops)

    # Filter by route_id
    route_filter = None
    if args.route_id:
        route_filter = [args.route_id]
    elif args.route_ids:
        route_filter = [r.strip() for r in args.route_ids.split(",") if r.strip()]
    if route_filter:
        if trips_df is None:
            raise SystemExit("Error: --trips required to filter by route_id")
        shapes_gdf = filter_shapes_by_route_and_direction(
            shapes_gdf, trips_df, route_filter, direction=args.direction
        )
        print(
            f"Filter applied: {len(shapes_gdf)} shapes matching route_id={route_filter}"
        )

    # Coloring
    if routes_df is not None and trips_df is not None:
        shapes_gdf = enrich_colors_from_routes(shapes_gdf, trips_df, routes_df)

    bbox = compute_bbox(shapes_gdf, padding_fraction=args.pad)
    bbox_used = plot_to_png(
        shapes_gdf,
        stops_gdf,
        out_png=args.out,
        dpi=args.dpi,
        linewidth=args.linewidth,
        bbox=bbox,
        scale=args.scale,
        route_color_map=args.color,
    )

    # Create structure for Leaflet
    leaflet_bounds = [[bbox_used[1], bbox_used[0]], [bbox_used[3], bbox_used[2]]]
    center_lat = (bbox_used[1] + bbox_used[3]) / 2
    center_lon = (bbox_used[0] + bbox_used[2]) / 2

    metadata = {
        "bounds": {
            "min_lon": bbox_used[0],
            "min_lat": bbox_used[1],
            "max_lon": bbox_used[2],
            "max_lat": bbox_used[3],
            "leaflet_bounds": leaflet_bounds,
            "center": [center_lat, center_lon],
        },
        "output_image": str(Path(args.out).resolve()),
        "filtered_routes": route_filter,
    }

    with open("overlay-metadata.json", "w") as f:
        json.dump(metadata, f, indent=2)

    # Display the ready-to-copy Leaflet line
    print("\n✅ Image generated:", args.out)
    print("📍 Leaflet coordinates:")
    print(json.dumps(leaflet_bounds, indent=2))
    print(f"➡️ Example JS:\n")
    print(
        f"L.imageOverlay('{Path(args.out).name}', {json.dumps(leaflet_bounds)}).addTo(map);"
    )
    print(f"map.fitBounds({json.dumps(leaflet_bounds)});")


if __name__ == "__main__":
    main()
