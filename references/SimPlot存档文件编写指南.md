# SimPlot2 存档文件编写指南

> 本文档描述 SimPlot2（Xojo 开发的桌面尺规兵棋绘图工具）存档文件的格式规范与编辑方法。
> 适用于在 SimPlot2 上运行任何尺规兵棋（含但不限于海战题材）时的存档读写。
> 本文档**不涉及任何具体兵棋的规则**，仅说明存档本身的格式与编辑技巧。

---

## 1. 概述

SimPlot2 以 **场景存档**（Scenario）为核心载体。一场推演的所有信息——当前时间、各方单位、单位位置/航向/航速、历史轨迹、显示设置——都保存在存档文件中。

- 软件安装目录：`SimPlot2-3 beta 19\`
- 场景目录：`Scenarios\`（存档默认存放处）
- 地图目录：`Maps\`（地图数据 + 图片）

### 存档文件类型

| 文件 | 视角 | 编码 | 说明 |
|---|---|---|---|
| `<场景名>.json` | Referee（裁判） | **明文 JSON** | 场景源文件，裁判全知视角 |
| `Blue.SpScn` | 蓝方 | 混淆 JSON | 蓝方视角存档 |
| `Red.SpScn` | 红方 | 混淆 JSON | 红方视角存档 |

> **重要机制**：软件保存场景时会同时写出以上多个文件，内容一致、仅 `File` 字段不同。
> 编辑时通常只需维护 `<场景名>.json`（裁判源文件），重新打开并保存一次后，软件会自动根据 json 重新生成 Blue/Red 两个 SpScn 文件。

---

## 2. 文件格式与编解码

### 2.1 编码规则

- **`.json` 文件**：标准明文 JSON 文本，UTF-8 编码，行尾 `\r\n`。
- **`.SpScn` 文件**：同样是 JSON 文本，但每个字节做 **ASCII −1** 混淆（加密），明文尾部追加 `\x0c\t` 两个标记字节。

**混淆示例**：

```
密文: |#Gjmf#;#Sfe#
明文: {"File":"Red"
```

（每个字符的 ASCII 码减 1：`|`→`{`，`#`→`"`，`G`→`F`……）

### 2.2 编解码工具（scn_tool.py）

工作区提供 Python 工具库，封装了全部编解码逻辑：

```python
from scn_tool import read_scn, write_scn, decode_raw, encode_raw

# 读取 .SpScn 文件 -> dict
data = read_scn('path/to/Red.SpScn')

# dict -> 写入 .SpScn 文件（自动混淆 + 尾部标记，与软件格式字节级一致）
write_scn('path/to/Red.SpScn', data)

# 读取明文 json
import json
data = json.loads(open('Scenarios/场景.json', 'rb').read().decode('utf-8'))
```

> 读取 `.SpScn` 时工具会自动容忍尾部 `\x0c\t` 标记；写入时会自动补上，保证软件可正常读取。

---

## 3. 存档文件结构

顶层字段（软件序列化顺序）：

```json
{
  "File": "Referee",              // 视角: Referee / Blue / Red
  "SimPlot Version": "2.3",
  "IsIntegerFile": true,
  "Scenario": { ... },            // 场景元数据
  "TypeOfGame": 0,
  "Time": { ... },                // 推演时间
  "Turns": [ ... ],               // 回合历史
  "Overlays": {},                 // 叠加标注层
  "Objects": [ "S001", ... ],     // 对象 ID 索引
  "Units": [ ... ],               // 单位数据（核心）
  "Formations": {}                // 编队
}
```

### 3.1 Scenario（场景元数据）

```json
"Scenario": {
  "ScenarioName": "123",          // 场景显示名
  "LastId": 4,                    // 最后对象序号
  "CurrentTrackNumber": 2409,     // 航迹编号计数器（软件自增，勿手改）
  "CurrentPlayerTrackNumber": 9000,
  "Phase": 0,                     // 阶段（见 §5.3）
  "TypeOfMap": 1,                 // 地图类型（见 §7）
  "MapFileName": "xxx.txt"        // 地图文件（TypeOfMap=1 时）
}
```

### 3.2 Time（时间）

```json
"Time": {
  "CurrentTurnTime": "2026-08-04 22:00:00",     // 当前回合时间
  "CurrentPositionTime": "2026-08-04 22:03:00", // 当前位置时间
  "CurrentTurnInterval": { "Minutes": 3, "Seconds": 0 }  // 回合时长
}
```

时间格式：`YYYY-MM-DD HH:MM:SS`（24 小时制）。

### 3.3 Turns（回合历史）

```json
"Turns": [
  { "TurnTime": "2026-08-04 22:00:00", "TurnInterval": { "Minutes": 3, "Seconds": 0 } },
  { "TurnTime": "2026-08-04 22:03:00", "TurnInterval": { "Minutes": 3, "Seconds": 0 } }
]
```

`Turns` 记录**已确认的回合**时间点列表，每次推进回合并确认后追加一条。

---

## 4. 单位数据模型

### 4.1 对象 ID 与类型前缀

`Objects` 数组中的 ID 前缀表示单位类别（可自定义，SimPlot 本身不限制）：

| 前缀 | 常见含义 | 示例 |
|---|---|---|
| `S` | 水面舰艇 | S001 |
| `A` | 飞机 | A007 |
| `U` | 潜艇 | U003 |
| `L` | 岸上设施 | L012 |

ID 命名规则：前缀 + 序号，如 `S001`、`S002`……`LastId` 记录最大序号。

### 4.2 Units 通用字段

```json
{
  "IdNum": "S001",                  // 对象 ID
  "Side": "Blue",                   // 阵营: Blue / Red / Neutral / Unknown
  "TrackNumber": 1555,              // 航迹编号
  "Name": "Orion",                  // 单位名称（可为空）
  "Number": 1,
  "UnitClass": "CL",                // 类型简码（如 CL/DD/BB/CV）
  "UnitType": "Cruiser",            // 类型全称（如 Cruiser/Destroyer/Battleship）
  "X": 157142, "Y": -13476190,      // 位置坐标（见 §5）
  "ShowSunk": false,                // 是否显示为沉没
  "IsActiveRadar": false,           // 雷达是否开机
  "IsActiveSonar": false,           // 声纳是否开机
  "PositionTimeCreated": "1941-03-28 07:30:00",  // 创建时间
  "PositionTimeDeleted": "1942-03-28 07:30:00",  // 删除时间（不存在则不显示）
  "Speed": 24000,                   // 航速（见 §5.2）
  "Course": 190000,                 // 航向（见 §5.2）
  "Range": -100000,
  "WpDistance": 0,
  "PastWaypointArray1": [],         // 历史轨迹点（见 §6）
  "FutureWaypointArray1": [],       // 未来航路点
  "TextTags": { ... }               // 标签显示设置（见 §4.4）
}
```

### 4.3 按类型附加字段

不同类别单位可携带额外字段：

| 类别 | 附加字段 | 含义 |
|---|---|---|
| 飞机 | `Altitude`, `AssignedAltitude`, `Climb`, `Descend` | 高度、指派高度、爬升率、下降率 |
| 潜艇 | `Depth`, `AssignedDepth`, `Ascend`, `Descend` | 深度、指派深度、上浮率、下潜率 |

### 4.4 TextTags（标签显示）

控制单位在图上的文字标签：

```json
"TextTags": {
  "TagName": true,          // 显示名称
  "TagTrackNum": false,     // 显示航迹编号
  "TagCourseSpeed": true,   // 显示航向/航速
  "TagClass": false,        // 显示类型
  "TagUnitType": false,
  "TagAltitude": false,     // 显示高度
  "TagDepth": false,        // 显示深度
  "TagCallsign": false,
  "AdditionalText": ""
}
```

常见组合：
- 显示名称 + 航向航速：`TagName:true, TagCourseSpeed:true`
- 显示航迹编号 + 名称：`TagTrackNum:true, TagName:true`

### 4.5 PerceptionArray（感知数据，可选）

裁判视角下单位被哪方感知到：

```json
"PerceptionArray": [
  { "PositionTimeStart": "...", "PositionTimeEnd": "...",
    "DetectionTime": "...", "SeenBySide": "Red", "ShowAsSide": "Blue",
    "ShowAsType": "Cruiser", "ShowAltitude": false, "ShowClass": false,
    "ShowCourseSpeed": false, "ShowDepth": false, "ShowName": false }
]
```

---

## 5. 坐标与数值编码

### 5.1 坐标系统 ⭐

- 坐标 `X`、`Y` 为**米制/海图单位**，以地图中心或指定原点为基准，`Y` 轴正方向为北。
- 文件存储值 = **实际值（海里）× 100000**（整数）。
- 显示换算：`显示值 = 文件值 / 100000`。

| 量 | 文件存储 | 实际值 |
|---|---|---|
| 位置 | 3975000 | 39.75（单位：海里） |
| 位置 | 25000 | 0.25（单位：海里） |

### 5.2 航速与航向（×1000 定点）

| 字段 | 存储规则 | 示例 |
|---|---|---|
| `Speed` | 节 × 1000 | 24000 = 24 节 |
| `Course` | 度 × 1000 | 190000 = 190.0°（罗盘角，0=北，顺时针） |

### 5.3 高度/深度（×1000 定点）

| 字段 | 存储规则 | 示例 |
|---|---|---|
| `Altitude` | 米 × 1000 | 10000000 = 10000 米 |
| `Depth` | 米 × 1000 | 50000 = 50 米 |

---

## 6. 轨迹（PastWaypointArray1）

轨迹 = 单位历史位置点数组，软件按点顺序连线绘制轨迹线。

**单个轨迹点格式**：

```json
["", X, Y, 0, 0, 高度/深度, 0, 0, 0, 1, true, "2026-08-04 22:00:00"]
```

| 索引 | 含义 |
|---|---|
| 0 | 点名称（空字符串） |
| 1 | X 坐标（文件单位） |
| 2 | Y 坐标 |
| 3-4 | 保留（0） |
| 5 | 高度/深度（飞机 Altitude / 潜艇 Depth / 水面 0） |
| 6-8 | 保留（0） |
| 9 | 类型标记（1） |
| 10 | 标志位（true） |
| 11 | 该点对应的时间戳 |

**规则**：
- 单位移动前，把当前位置写入 `PastWaypointArray1`。
- 一个回合内发生转向时，可写入多个中间点（前冲点、转向点），轨迹呈折线。
- 轨迹时间/回合时间标注依赖点的时间戳。

---

## 7. 地图配置

`Scenario` 中的地图字段：

| TypeOfMap | 含义 | 是否需 MapFileName |
|---|---|---|
| `0` | 默认/无地图（网格背景） | 否 |
| `1` | 自定义地图 | 是，指向 `Maps/` 下的 `.txt` 描述文件 |

地图描述文件（`Maps/*.txt`）格式：

```
MAP=Indian Interception.png
SCALE=3.071
```

- `MAP`：地图图片文件名（同目录下 PNG）
- `SCALE`：比例尺（千米/像素）

配套地图图片：`Maps/*.png`。

> 单位坐标与地图范围需匹配，否则单位会显示在地图外。无配套地图时使用 `TypeOfMap=0`。

---

## 8. 时间推进与回合状态（Do/Next 机制）⭐

SimPlot 的回合推进由 **Do / Undo / Next** 三个按钮驱动，存档中的时间字段精确反映当前状态：

| 操作 | CurrentTurnTime | CurrentPositionTime | Phase | 说明 |
|---|---|---|---|---|
| 初始/未操作 | = 起始时间 | = 起始时间 | 0 | 规划阶段 |
| **Do**（单位移动） | **不变** | 推进（+回合时长） | 2 | 移动已发生，未确认，可 Undo |
| **Next**（确认回合） | 推进至 = PositionTime | 不变 | **0** | 回合确认，回到规划阶段 |

- `CurrentTurnTime`：当前回合时间（Do 不改变，Next 后追上 PositionTime）
- `CurrentPositionTime`：单位位置对应的时间（Do 时推进）
- `Phase`：0 = 规划（plotting）；2 = 移动后（post-movement）
- `Turns`：已确认回合列表，Next 时**追加**一条当前回合时间

### 存档状态识别

可根据时间字段组合判断存档处于哪个阶段：

| TurnTime vs PositionTime | 有无轨迹点 | 状态 |
|---|---|---|
| 相等 | 无 | 初始（规划阶段） |
| 不相等 | 有 | Do 后（已移动未确认） |
| 相等 | 有 | Do+Next（已确认，回到规划） |

### 保存状态约定

AI 生成的"推进回合"存档通常模拟 **Do 后状态**：
- `CurrentTurnTime` 保持原值不变
- `CurrentPositionTime` 推进（+= 回合时长）
- `Phase = 2`
- `Turns` 保持原样

用户可在软件中自行点击 Next 确认回合。

---

## 9. 存档文件命名规范

推进回合生成新存档时，**不要覆盖旧存档**，命名规则：

```
<存档名>-<PositionTime 紧凑格式>.json
```

示例：`冰海巨兽-1939-11-25-13-03-00.json`
（PositionTime 中的冒号/空格替换为 `-`，与 `ScenarioName` 保持一致）

---

## 10. 常见编辑操作示例

### 10.1 新增单位

```python
import json

data = json.loads(open('Scenarios/场景.json', 'rb').read().decode('utf-8'))
new_unit = {
    "IdNum": "S004",
    "Side": "Blue",
    "TrackNumber": 2405,
    "Name": "新单位",
    "Number": 1,
    "UnitClass": "BB",
    "UnitType": "Battleship",
    "X": 3108975, "Y": 525000,
    "ShowSunk": False,
    "IsActiveRadar": False, "IsActiveSonar": False,
    "PositionTimeCreated": data['Time']['CurrentPositionTime'],
    "PositionTimeDeleted": "2027-08-04 22:00:00",
    "Speed": 25000, "Course": 10000,
    "Range": -100000, "WpDistance": 0,
    "PastWaypointArray1": {}, "FutureWaypointArray1": {},
    "TextTags": {"TagName": True, "TagCourseSpeed": True, "TagTrackNum": False,
                 "TagAltitude": False, "TagClass": False, "TagCallsign": False,
                 "TagDepth": False, "TagUnitType": False, "AdditionalText": ""},
}
data['Objects'].append("S004")
data['Units'].append(new_unit)
data['Scenario']['LastId'] = 4
open('Scenarios/场景.json', 'wb').write(
    json.dumps(data, ensure_ascii=False, separators=(',', ':')).encode('utf-8') + b'\r\n')
```

### 10.2 修改单位坐标

```python
for u in data['Units']:
    if u['IdNum'] == 'S004':
        u['X'] = 3108975
        u['Y'] = 525000
```

### 10.3 写入 .SpScn 文件

```python
from scn_tool import write_scn
write_scn('Scenarios/Blue.SpScn', data)
```

---

## 11. 注意事项

1. **坐标/速度/高度/深度的定点倍率**（×100000 / ×1000）极易出错，务必先换算再写入。
2. `CurrentTrackNumber` 由软件自增维护，不要手工修改。
3. 时间格式严格为 `YYYY-MM-DD HH:MM:SS`。
4. 新增单位后同步更新 `Objects` 与 `Scenario.LastId`。
5. 修改存档后需在软件中**重新加载场景**才能看到变化；保存一次 json 后 Blue/Red 自动重建。
6. 写 `.SpScn` 必须保留尾部 `\x0c\t` 标记（工具已自动处理）。
7. 军事时间表述常省略冒号（如 `1300` = 13:00），解析用户输入时须注意。
