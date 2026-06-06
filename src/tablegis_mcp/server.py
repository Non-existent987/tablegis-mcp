"""TableGIS MCP Server.

Exposes tablegis geospatial processing functions as MCP tools so that AI
assistants (Claude, ChatGPT, etc.) can perform spatial analysis through
natural language.

Data is passed as CSV/JSON strings and returned as JSON.  Geometry columns
are serialised as WKT so they remain portable across clients.
"""

from __future__ import annotations

import io
import warnings
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd
import tablegis as tg
from mcp.server.fastmcp import FastMCP
from shapely import wkt as shapely_wkt

mcp = FastMCP("tablegis", instructions=(
    "TableGIS MCP Server – geospatial data processing tools.\n"
    "All tools accept tabular data as a CSV or JSON string and return results "
    "as JSON. Geometry columns are returned as WKT strings.\n"
    "Distances are in metres; coordinates default to WGS-84 (EPSG:4326)."
))

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _to_python_native(val: Any) -> Any:
    """Convert numpy/shapely types to JSON-serializable Python natives."""
    if val is None:
        return None
    try:
        if pd.isna(val):
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(val, "wkt"):
        return val.wkt
    if isinstance(val, (np.integer,)):
        return int(val)
    if isinstance(val, (np.floating,)):
        return float(val)
    if isinstance(val, np.ndarray):
        return val.tolist()
    return val


def _parse_dataframe(data: str) -> pd.DataFrame:
    """Parse a CSV or JSON string into a DataFrame."""
    data = data.strip()
    if not data:
        raise ValueError("Input data is empty")
    if data.startswith("[") or data.startswith("{"):
        return pd.read_json(io.StringIO(data))
    return pd.read_csv(io.StringIO(data))


def _serialize_result(result: pd.DataFrame | gpd.GeoDataFrame) -> str:
    """Serialize a DataFrame / GeoDataFrame to a JSON string.

    Geometry columns are converted to WKT; all other columns are kept as-is.
    """
    if isinstance(result, gpd.GeoDataFrame):
        result = result.copy()
        # Convert all geometry columns to WKT strings, then treat as plain DataFrame
        geom_cols = [col for col in result.columns
                     if isinstance(result[col].dtype, gpd.array.GeometryDtype)]
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            for col in geom_cols:
                result[col] = result[col].apply(
                    lambda g: g.wkt if g is not None and hasattr(g, "wkt") else None
                )
        result = pd.DataFrame(result)
    # Convert non-serializable types (numpy ints/floats) to native Python types
    result = result.copy()
    if len(result) > 0:
        for col in result.columns:
            result[col] = result[col].apply(_to_python_native)
    return result.to_json(orient="records", force_ascii=False)


def _gdf_from_json_with_geometry(data: str, geometry_col: str = "geometry",
                                  crs: str = "EPSG:4326") -> gpd.GeoDataFrame:
    """Parse JSON that contains a WKT geometry column into a GeoDataFrame."""
    data = data.strip()
    if not data:
        raise ValueError("Input data is empty")
    df = pd.read_json(io.StringIO(data))
    if geometry_col in df.columns:
        df[geometry_col] = df[geometry_col].apply(
            lambda w: shapely_wkt.loads(w) if pd.notna(w) and isinstance(w, str) else None
        )
    return gpd.GeoDataFrame(df, geometry=geometry_col, crs=crs)


# ===========================================================================
# MCP Tools
# ===========================================================================

@mcp.tool()
def nearest_neighbor_one_table(
    data: str,
    lon: str = "lon",
    lat: str = "lat",
    idname: str = "id",
    n: int = 1,
    include_self: bool = False,
) -> str:
    """Find the nearest n neighbors for each point in a dataset.

    Given a table of points with longitude/latitude columns, computes the
    nearest n neighbors for every row using a KD-tree.  Returns the original
    columns plus nearest-neighbor ids, coordinates and distances (metres).

    Parameters
    ----------
    data : str
        Input table as CSV or JSON string.  Must contain the columns
        referenced by lon, lat and idname.
    lon : str
        Longitude column name (default "lon").
    lat : str
        Latitude column name (default "lat").
    idname : str
        Identifier column name (default "id").
    n : int
        Number of nearest neighbors to find (default 1).
    include_self : bool
        Whether to include the point itself among neighbors (default False).
    """
    df = _parse_dataframe(data)
    result = tg.min_distance_onetable(df, lon=lon, lat=lat, idname=idname,
                                       n=n, include_self=include_self)
    return _serialize_result(result)


@mcp.tool()
def nearest_neighbor_two_tables(
    data1: str,
    data2: str,
    lon1: str = "lon",
    lat1: str = "lat",
    lon2: str = "lon",
    lat2: str = "lat",
    df2_id: str = "id",
    n: int = 1,
) -> str:
    """Compute distances from each point in data1 to the nearest n points in data2.

    Uses a KD-tree for efficient nearest-neighbor searches.  Both datasets
    should use WGS-84 (EPSG:4326) coordinates.  Distances are in metres.

    Parameters
    ----------
    data1 : str
        Source table (CSV or JSON) containing query points.
    data2 : str
        Target table (CSV or JSON) containing reference points.
    lon1, lat1 : str
        Longitude/latitude column names in data1 (default "lon"/"lat").
    lon2, lat2 : str
        Longitude/latitude column names in data2 (default "lon"/"lat").
    df2_id : str
        Identifier column in data2 (default "id").
    n : int
        Number of nearest neighbors to find (default 1).
    """
    df1 = _parse_dataframe(data1)
    df2 = _parse_dataframe(data2)
    result = tg.min_distance_twotable(df1, df2, lon1=lon1, lat1=lat1,
                                       lon2=lon2, lat2=lat2, df2_id=df2_id, n=n)
    return _serialize_result(result)


@mcp.tool()
def create_buffer(
    data: str,
    lon: str = "lon",
    lat: str = "lat",
    dis: float = 1000,
    min_distance: float | None = None,
    geometry: str = "geometry",
) -> str:
    """Create accurate buffers in metres around points.

    Projects to an appropriate UTM zone for metre-based accuracy, then
    converts back to WGS-84.  Supports ring buffers (donut shape) when
    min_distance is provided.

    Parameters
    ----------
    data : str
        Input table (CSV or JSON) with lon/lat columns.
    lon, lat : str
        Longitude/latitude column names (default "lon"/"lat").
    dis : float
        Outer buffer distance in metres (default 1000).
    min_distance : float, optional
        Inner radius for ring buffers in metres.  If None, creates a filled
        circle.
    geometry : str
        Name for the output geometry column (default "geometry").
    """
    df = _parse_dataframe(data)
    result = tg.add_buffer(df, lon=lon, lat=lat, dis=dis,
                            min_distance=min_distance, geometry=geometry)
    return _serialize_result(result)


@mcp.tool()
def create_polygon(
    data: str,
    lon: str = "lon",
    lat: str = "lat",
    num_sides: int = 4,
    radius: float | None = None,
    side_length: float | None = None,
    interior_angle: float | None = None,
    rotation: float = 0.0,
    geometry: str = "geometry",
) -> str:
    """Create regular polygons (or star polygons) around points.

    Projects to UTM for metre-based accuracy, outputs WGS-84 WKT.

    Parameters
    ----------
    data : str
        Input table (CSV or JSON) with lon/lat columns.
    lon, lat : str
        Longitude/latitude column names (default "lon"/"lat").
    num_sides : int
        Number of polygon sides, >= 3 (default 4).
    radius : float, optional
        Outer radius in metres.  Either radius or side_length must be given.
    side_length : float, optional
        Side length in metres.  If given (and radius is None), radius is
        computed automatically.
    interior_angle : float, optional
        Interior angle in degrees for star/concave polygons.
    rotation : float
        Additional rotation in degrees (default 0).
    geometry : str
        Output geometry column name (default "geometry").
    """
    df = _parse_dataframe(data)
    result = tg.add_polygon(df, lon=lon, lat=lat, num_sides=num_sides,
                             radius=radius, side_length=side_length,
                             interior_angle=interior_angle, rotation=rotation,
                             geometry=geometry)
    return _serialize_result(result)


@mcp.tool()
def create_sector(
    data: str,
    lon: str = "lon",
    lat: str = "lat",
    azimuth: float = 0,
    distance: float = 1000,
    angle: float = 60,
    difference_distance: float | None = None,
    geometry: str = "geometry",
) -> str:
    """Create sector (wedge) polygons around points.

    Useful for modelling directional coverage such as cell-tower sectors or
    radar beams.  Projects to UTM for metre accuracy, outputs WGS-84 WKT.

    Parameters
    ----------
    data : str
        Input table (CSV or JSON) with lon/lat columns.
    lon, lat : str
        Longitude/latitude column names (default "lon"/"lat").
    azimuth : float
        Bearing in degrees (0 = north, clockwise) (default 0).
    distance : float
        Outer radius in metres (default 1000).
    angle : float
        Total sector angle in degrees (default 60).
    difference_distance : float, optional
        Inner radius for ring-sector in metres.
    geometry : str
        Output geometry column name (default "geometry").
    """
    df = _parse_dataframe(data)
    result = tg.add_sectors(df, lon=lon, lat=lat, azimuth=azimuth,
                             distance=distance, angle=angle,
                             difference_distance=difference_distance,
                             geometry=geometry)
    return _serialize_result(result)


@mcp.tool()
def points_to_geodataframe(
    data: str,
    lon: str = "lon",
    lat: str = "lat",
    geometry: str = "geometry",
    crs: str = "epsg:4326",
) -> str:
    """Convert a table with lon/lat columns to a GeoDataFrame of Points.

    Parameters
    ----------
    data : str
        Input table (CSV or JSON) with lon/lat columns.
    lon, lat : str
        Longitude/latitude column names (default "lon"/"lat").
    geometry : str
        Name for the output geometry column (default "geometry").
    crs : str
        Coordinate reference system (default "epsg:4326").
    """
    df = _parse_dataframe(data)
    result = tg.add_points(df, lon=lon, lat=lat, geometry=geometry, crs=crs)
    return _serialize_result(result)


@mcp.tool()
def calculate_area(
    data: str,
    geometry_col: str = "geometry",
    column: str = "add_area",
    crs_epsg: int | None = None,
    area_type: str = "int",
) -> str:
    """Calculate the area of polygon geometries in square metres.

    Temporarily projects to an appropriate UTM zone for accurate area
    computation, then converts back to the original CRS.

    Parameters
    ----------
    data : str
        Input JSON string with a WKT geometry column.
    geometry_col : str
        Name of the geometry column (default "geometry").
    column : str
        Name for the output area column (default "add_area").
    crs_epsg : int, optional
        EPSG code for the projection to use.  If None, UTM is auto-selected.
    area_type : str
        "int" or "float" for the output data type (default "int").
    """
    gdf = _gdf_from_json_with_geometry(data, geometry_col=geometry_col)
    result = tg.add_area(gdf, column=column, crs_epsg=crs_epsg,
                          area_type=area_type)
    return _serialize_result(result)


@mcp.tool()
def buffer_geometries(
    data: str,
    distance: float,
    geometry_col: str = "geometry",
) -> str:
    """Expand or shrink existing geometries by a buffer distance in metres.

    Takes a GeoDataFrame with existing polygon/point geometries, projects to
    UTM, applies the buffer, and converts back to WGS-84.

    Parameters
    ----------
    data : str
        Input JSON string with a WKT geometry column.
    distance : float
        Buffer distance in metres.  Positive = expand, negative = shrink.
    geometry_col : str
        Name of the geometry column (default "geometry").
    """
    gdf = _gdf_from_json_with_geometry(data, geometry_col=geometry_col)
    result = tg.buffer(gdf, distance=distance, geometry_col=geometry_col)
    return _serialize_result(result)


@mcp.tool()
def cluster_by_distance(
    data: str,
    lon: str = "lon",
    lat: str = "lat",
    distance: float = 50,
    columns_name: str = "clusterid",
    id_label_prefix: str = "cluster_",
    geom: bool = False,
) -> str:
    """Group points into clusters by buffer distance and assign cluster IDs.

    Creates buffers around points, dissolves overlapping buffers into cluster
    polygons, and assigns each point a cluster ID.

    Parameters
    ----------
    data : str
        Input table (CSV or JSON) with lon/lat columns.
    lon, lat : str
        Longitude/latitude column names (default "lon"/"lat").
    distance : float
        Buffer distance in metres for grouping (default 50).
    columns_name : str
        Name of the output cluster ID column (default "clusterid").
    id_label_prefix : str
        Prefix for cluster labels, e.g. "cluster_0" (default "cluster_").
    geom : bool
        If True, include cluster polygon geometry in output (default False).
    """
    df = _parse_dataframe(data)
    result = tg.add_buffer_groupbyid(df, lon=lon, lat=lat, distance=distance,
                                      columns_name=columns_name,
                                      id_label_prefix=id_label_prefix,
                                      geom=geom)
    return _serialize_result(result)


@mcp.tool()
def convert_coordinates(
    data: str,
    lon: str = "lon",
    lat: str = "lat",
    from_crs: str = "wgs84",
    to_crs: str = "gcj02",
) -> str:
    """Convert coordinates between Chinese coordinate systems.

    Supports: wgs84 (EPSG:4326), gcj02 (Mars/高德), bd09 (百度),
    web_mercator (EPSG:3857), cgcs2000 (EPSG:4490).

    Parameters
    ----------
    data : str
        Input table (CSV or JSON) with lon/lat columns.
    lon, lat : str
        Longitude/latitude column names (default "lon"/"lat").
    from_crs : str
        Source CRS name: "wgs84", "gcj02", "bd09", "web_mercator", "cgcs2000"
        (default "wgs84").
    to_crs : str
        Target CRS name, same options as from_crs (default "gcj02").
    """
    df = _parse_dataframe(data)
    result = tg.to_lonlat(df, lon=lon, lat=lat, from_crs=from_crs,
                           to_crs=to_crs)
    return _serialize_result(result)


@mcp.tool()
def match_spatial_layer(
    data: str,
    layer_path: str,
    lon: str = "lon",
    lat: str = "lat",
    columns: str | None = None,
    default_value: str | float | None = None,
    match_method: str = "one",
    sep: str = ",",
    predicate: str = "intersects",
) -> str:
    """Match points to a spatial layer (shapefile/GeoJSON) and add attributes.

    Performs a spatial join between the input points and a polygon layer,
    adding columns from the layer to the point data.

    Parameters
    ----------
    data : str
        Input table (CSV or JSON) with lon/lat columns.
    layer_path : str
        Path to a spatial file (shp, geojson, gpkg, etc.).
    lon, lat : str
        Longitude/latitude column names (default "lon"/"lat").
    columns : str, optional
        Comma-separated column names from the layer to add.  If None, adds all.
    default_value : str or float, optional
        Fill value for points with no match.
    match_method : str
        "one" = first match, "multi_cell" = join values with separator,
        "multi_row" = expand rows (default "one").
    sep : str
        Separator for multi_cell mode (default ",").
    predicate : str
        Spatial predicate: "intersects", "within", "contains", etc.
        (default "intersects").
    """
    df = _parse_dataframe(data)
    cols = [c.strip() for c in columns.split(",")] if columns else None
    result = tg.match_layer(df, layer=layer_path, lon=lon, lat=lat,
                             columns=cols, default_value=default_value,
                             match_method=match_method, sep=sep,
                             predicate=predicate)
    return _serialize_result(result)


# ===========================================================================
# Entry point
# ===========================================================================

def main():
    """Run the TableGIS MCP server."""
    mcp.run()


if __name__ == "__main__":
    main()
