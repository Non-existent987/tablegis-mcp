# tablegis-mcp

[English](README.md) | [简体中文](README.zh-CN.md)

`tablegis-mcp` 是 [tablegis](https://github.com/Non-existent987/tablegis) 的 MCP Server 封装，将地理空间数据处理能力暴露为 MCP 工具，使 AI 助手（Claude、ChatGPT、Cursor 等）能通过自然语言直接调用 GIS 分析功能。

## 为什么需要这个？

以前用 tablegis，你得自己写 Python 代码。现在只需对 AI 说"帮我找最近的3个邻居"或"画3公里配送圈"，AI 就会自动调用 tablegis 完成计算。

## 工具列表

| 工具 | 说明 |
|------|------|
| `nearest_neighbor_one_table` | 在单个数据集内，为每个点找最近的 n 个邻居 |
| `nearest_neighbor_two_tables` | 为数据集 A 的每个点，找数据集 B 中最近的 n 个点 |
| `create_buffer` | 在点周围创建圆形或环形缓冲区（单位：米） |
| `create_polygon` | 在点周围创建正多边形或星形多边形 |
| `create_sector` | 在点周围创建扇形（楔形）多边形，用于信号覆盖等场景 |
| `points_to_geodataframe` | 将经纬度列转为 Point 几何对象 |
| `calculate_area` | 计算多边形面积（单位：平方米） |
| `buffer_geometries` | 对已有几何对象进行扩大或缩小 |
| `cluster_by_distance` | 按距离将邻近的点聚类并分配聚类 ID |
| `convert_coordinates` | 坐标系转换（WGS84/GCJ02/BD09/CGCS2000/Web Mercator） |
| `match_spatial_layer` | 空间连接：将点匹配到矢量图层（shp/GeoJSON）并添加属性 |
| `fast_read_table` | 大型Excel/CSV快速读取（Parquet缓存加速，快10-50倍） |

## 安装

```bash
pip install tablegis-mcp
```

或使用 `uvx` 免安装直接运行：

```bash
uvx tablegis-mcp
```

## 配置

### Claude Desktop

在 `claude_desktop_config.json` 中添加：

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

或通过 pip 安装后：

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

在 `~/.claude.json`（全局）或项目级 `.claude/settings.json` 中添加：

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

或：

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

### Cursor / 其他 MCP 客户端

使用相同的命令配置，服务器通过 stdio 传输协议通信。

## 使用示例

配置完成后，你可以直接对 AI 助手说：

### 1、最近邻查询

> "帮我算这3个门店之间的最近邻关系：id,lon,lat 1,116.4,39.9 2,116.5,39.95 3,116.45,39.92"

> "我的门店和竞品门店两份数据，帮我算每家店最近的3个竞品是谁、多远"

### 2、缓冲区生成

> "在这些站点周围画500米的配送范围"

> "画3公里的环形缓冲区，内半径1公里，外半径3公里"

### 3、扇形覆盖

> "基站数据有方位角、覆盖距离和扇形角度，帮我画出每个基站的信号覆盖区域"

### 4、面积计算

> "帮我算每个地块的面积，单位平方米"

### 5、聚类

> "把距离500米以内的门店归到同一个商圈，给每个商圈编个号"

### 6、坐标系转换

> "把这份数据的 WGS84 坐标转成高德坐标系（GCJ-02）"

> "把百度坐标（BD-09）转成 WGS84"

### 7、空间属性匹配

> "把这些坐标点匹配到行政区划 shapefile，把区名加进来"

### 8、大型文件快速读取

> "读取这个规划数据文件的站点信息sheet"

> "加载这个Excel文件，只需要城市和经纬度这几列"

**`fast_read_table` — 大型Excel/CSV快速读取**

使用 Polars + Calamine（Rust引擎）解析Excel，比 openpyxl 快 10-50 倍。首次读取后自动缓存为 Parquet 格式，后续加载接近瞬时完成。**指定sheet时只转换该sheet，不会转换其他sheet**。

**参数：**

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `file` | str | 必填 | Excel或CSV文件路径 |
| `sheet` | str | None | sheet名称（仅Excel），None=全部sheet |
| `columns` | str | None | 只加载指定列，逗号分隔（如"城市,经度,纬度"） |
| `refresh` | bool | False | 强制重新转换（源文件更新后使用） |
| `to_pandas` | bool | True | 返回JSON记录（True）或元数据摘要（False） |

**性能对比**（290万行、10个sheet、321MB Excel文件）：

| 方法 | 单sheet（14.7万行） | 全量（290万行） |
|------|---------------------|----------------|
| `pandas.read_excel` | 244秒 | ~40分钟 |
| `fast_read_table`（首次） | ~5秒 | ~2.5分钟 |
| `fast_read_table`（缓存） | **0.02秒** | **0.12秒** |

## 数据格式说明

- **输入**：CSV 或 JSON 字符串，必须包含经纬度列
- **输出**：JSON 格式，几何列以 WKT 字符串返回
- **距离单位**：米
- **默认坐标系**：WGS-84（EPSG:4326）

## 开发

```bash
git clone https://github.com/Non-existent987/tablegis-mcp.git
cd tablegis-mcp
pip install -e ".[dev]"
```

## 许可证

MIT