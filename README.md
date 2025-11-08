# 🚌 GTFS Bus Line Renderer

This repository contains a Python script that generates a PNG map visualization of a bus line using GTFS (General Transit Feed Specification) data. The script parses GTFS files (routes, trips, shapes, and stops) to render a clean, high-quality image of a selected bus route — perfect for documentation, presentations, or transit data analysis.

## Features

- Reads standard GTFS datasets (routes.txt, trips.txt, shapes.txt, stops.txt)
- Plots the full route path and stops on a map
- Exports the output as a PNG image
- Customizable colors, line thickness, and map size

## Usage
```python
python gtfs_to_png.py --shapes shapes.txt --trips trips.txt --routes routes.txt \
    --route_id 6638 --out line84.png --dpi 400 --scale 5
```

## Output example

### Image
![Line84](./line84.png)

### Data
```json
{
  "bounds": {
    "min_lon": -123.25216578,
    "min_lat": 49.26503236,
    "max_lon": -123.07594922000001,
    "max_lat": 49.27374964,
    "leaflet_bounds": [
      [
        49.26503236,
        -123.25216578
      ],
      [
        49.27374964,
        -123.07594922000001
      ]
    ],
    "center": [
      49.269391,
      -123.16405750000001
    ]
  },
  "output_image": "line84.png",
  "filtered_routes": [
    "6638"
  ]
}
```