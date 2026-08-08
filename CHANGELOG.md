# Changelog

本文件格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

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
