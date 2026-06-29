# TableGIS MCP Server

[English](README.md) | [简体中文](README.zh-CN.md)

Geospatial data processing tools for AI assistants via the [Model Context Protocol (MCP)](https://modelcontextprotocol.io/).

Wraps [tablegis](https://github.com/Non-existent987/tablegis) functions as MCP tools, enabling AI clients (Claude Desktop, Cursor, etc.) to perform spatial analysis through natural language.

## Tools

| Tool | Description |
|------|-------------|
| `nearest_neighbor_one_table` | Find nearest n neighbors within a single point dataset |
| `nearest_neighbor_two_tables` | Find nearest n points from dataset B for each point in dataset A |
| `create_buffer` | Create circular or ring buffers around points (metres) |
| `create_polygon` | Create regular or star polygons around points |
| `create_sector` | Create sector (wedge) polygons for directional coverage |
| `points_to_geodataframe` | Convert lon/lat columns to Point geometries |
| `calculate_area` | Calculate polygon areas in square metres |
| `buffer_geometries` | Expand/shrink existing geometries by a distance |
| `cluster_by_distance` | Group nearby points into clusters by buffer distance |
| `convert_coordinates` | Convert between Chinese coordinate systems (WGS84/GCJ02/BD09) |
| `match_spatial_layer` | Spatial join: match points to a polygon layer file |
| `fast_read_table` | Read large Excel/CSV files with Parquet caching (10-50x faster) |

## Install

```bash
pip install tablegis-mcp
```

Or use with `uvx` (no install needed):

```bash
uvx tablegis-mcp
```

## Configure

### Claude Desktop

Add to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "tablegis": {
      "command": "uvx",
      "args": ["tablegis-mcp"]
    }
  }
}
```

Or if installed via pip:

```json
{
  "mcpServers": {
    "tablegis": {
      "command": "python",
      "args": ["-m", "tablegis_mcp.server"]
    }
  }
}
```

### Claude Code

Add to `~/.claude.json` (global) or project-level `.claude/settings.json`:

```json
{
  "mcpServers": {
    "tablegis": {
      "command": "uvx",
      "args": ["tablegis-mcp"]
    }
  }
}
```

Or with pip:

```json
{
  "mcpServers": {
    "tablegis": {
      "command": "python",
      "args": ["-m", "tablegis_mcp.server"]
    }
  }
}
```

### Cursor / Other MCP Clients

Use the same command configuration. The server communicates via stdio transport.

## Usage Examples

Once configured, you can ask your AI assistant:

- "Find the 3 nearest neighbors for each point in this dataset"
- "Draw 3km delivery zones around these store locations"
- "Calculate the area of each polygon in square metres"
- "Group points within 500m into clusters"
- "Match these coordinates to a shapefile of administrative boundaries"
- "Convert these WGS84 coordinates to GCJ-02 (Amap/高德)"
- "Read this large Excel file and show me the first 10 rows"
- "Load the 站点信息 sheet from the planning data file"

Data is passed as CSV or JSON strings; geometry results are returned as WKT.

### `fast_read_table` — Fast Large File Reading

This tool reads Excel (.xlsx/.xlsb) and CSV files using Polars + Calamine (Rust engine), which is 10-50x faster than openpyxl. The first read automatically caches data as Parquet; subsequent reads load from cache in milliseconds. **Only the requested sheet is converted** — other sheets are not touched.

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `file` | str | required | Path to the Excel or CSV file |
| `sheet` | str | None | Sheet name (Excel only). None = all sheets |
| `columns` | str | None | Comma-separated column names to load (e.g. "城市,经度,纬度") |
| `refresh` | bool | False | Force re-convert after source file is updated |
| `to_pandas` | bool | True | Return as JSON records (True) or metadata summary (False) |

**Examples:**

```
"Read the 站点信息 sheet from /data/planning.xlsx"
→ fast_read_table(file="/data/planning.xlsx", sheet="站点信息")

"Load only the city and coordinates columns"
→ fast_read_table(file="/data/planning.xlsx", sheet="站点信息", columns="城市,经度,纬度")

"Read all sheets from this Excel file"
→ fast_read_table(file="/data/planning.xlsx")
```

**Performance** (290M rows, 10 sheets, 321MB Excel):

| Method | Single sheet (147K rows) | All sheets (2.9M rows) |
|--------|-------------------------|------------------------|
| `pandas.read_excel` | 244s | ~40min |
| `fast_read_table` (first time) | ~5s | ~2.5min |
| `fast_read_table` (cached) | **0.02s** | **0.12s** |

## Development

```bash
git clone https://github.com/Non-existent987/tablegis-mcp.git
cd tablegis-mcp
pip install -e ".[dev]"
```

## License

MIT