# Changelog

本文件格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [1.2.0] - 2026-08-09

### 新增

- **飞机生命周期规则**：剧本初设时未起飞飞机不建立单位，写入存档顶层 `NotLaunchedAircraft` 清单；起飞时新建飞机单位（低空 200 米、全功率 25% 航速、航向同母舰，HarpoonV §7.2；起飞当回合不移动），降落时移除单位并回写清单（信息不丢失）；剧本推演命令表始终保留全部飞机信息（含未起飞）
- 新增 `scn_tool` 辅助函数：`mk_air_unit` / `mk_roster_entry` / `add_unit` / `remove_unit` / `roster_add` / `roster_remove` / `launched_add` / `launched_remove` / `find_unit`（Units/Objects 同步增删、TrackNumber/LastId 自动维护）
- 剧本推演命令表飞机表新增"所属母舰/基地"列：未起飞行当前状态=未起飞、当前速度/航向/高度=—、最大速度预填；飞行中行当前列=实际值
- 自然语言指令新增"起飞/放飞<飞机名>"（新建单位）与"降落"/"降落至<单位名>"（移除单位并回写清单）；高度解析扩展支持"起飞到X米"

## [1.1.0] - 2026-08-08

### 修复

- 按 HarpoonV 规则修正 D/E 级转向损失（D 级 200码/1节、E 级 100码/2节）
- 新增 F/G 尺寸等级，补充天气、损伤、飞机相关规则
- 同步更新移动计算指南、`scn_tool.py` 及剧本推演命令表示例

## [1.0.0] - 2026-08-06

### 新增

- 首个可用版本：SimPlot 鱼叉·海上指挥推演存档工具 skill
  - 直接读写 SimPlot2 存档：`.json` 明文 + `.SpScn` 混淆编码
  - 内置 Harpoon V（鱼叉）/ Command at Sea（海上指挥）运动规则
  - 支持水面舰艇、潜艇（水上/静航/非静航）、飞机
  - 自然语言指令推进回合、生成剧本初设表
  - 脚本：`scn_tool.py`（核心库）、`simplot_cmd.py`（指令系统）
  - 参考资料与示例剧本：极地行动、冰海巨兽、拉普拉塔河口海战
