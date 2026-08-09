"""
SimPlot2 SpScn 存档文件编解码与操作工具库
格式: JSON 文本, 每个字节 ASCII-1 混淆; .SpScn 尾部明文 \\x0c\\t, .json 尾部 \\r\\n
坐标: 文件 X/Y = 海里 × 100000
全部函数参数化, 无硬编码路径 —— 可移植到任意电脑
"""
import json, os, math, copy, datetime

# ---------- 编解码 ----------
def decode_raw(raw: bytes) -> bytes:
    """SpScn 密文 -> 明文 JSON 字节 (每字节 ASCII-1)"""
    return bytes((b - 1) & 0xFF for b in raw)

def encode_raw(plain: bytes) -> bytes:
    """明文 JSON 字节 -> SpScn 密文字节 (每字节 ASCII+1)"""
    return bytes((b + 1) & 0xFF for b in plain)

def read_json(path: str) -> dict:
    """读取明文 .json 存档 (Referee 视角, 尾部 \\r\\n)"""
    with open(path, 'rb') as f:
        raw = f.read()
    return json.loads(raw.decode('utf-8').rstrip())

def read_scn(path: str) -> dict:
    """读取 .SpScn 存档 (ASCII-1 混淆, 容忍尾部 \\x0c\\t 标记)"""
    with open(path, 'rb') as f:
        raw = f.read()
    plain = decode_raw(raw).decode('utf-8', errors='replace')
    return json.loads(plain.rstrip())

def write_json(path: str, data: dict) -> None:
    """dict -> 写入明文 .json (尾部 \\r\\n)"""
    plain = json.dumps(data, ensure_ascii=False, separators=(',', ':')) + '\r\n'
    with open(path, 'wb') as f:
        f.write(plain.encode('utf-8'))

def write_scn(path: str, data: dict) -> None:
    """dict -> 写入 .SpScn (JSON + \\x0c\\t 标记 + ASCII-1 加密)"""
    plain = json.dumps(data, ensure_ascii=False, separators=(',', ':')) + '\x0c\t'
    with open(path, 'wb') as f:
        f.write(encode_raw(plain.encode('utf-8')))

def load_scenario(path: str) -> dict:
    """按扩展名自动选择读取方式 (json 明文 / SpScn 混淆)"""
    return read_scn(path) if path.lower().endswith('.spscn') else read_json(path)

# ---------- 坐标换算 (1 文件单位 = 1/100000 海里) ----------
NMI_SCALE = 100000
YARDS_PER_NMI = 2025.37  # 1 海里 = 2025.37 码

def nm_to_file(nmi: float) -> int:
    """海里 -> 文件坐标 (×100000, 四舍五入)"""
    return int(round(nmi * NMI_SCALE))

def file_to_nm(fcoord) -> float:
    """文件坐标 -> 海里"""
    return float(fcoord) / NMI_SCALE

def yard_to_file(yards: float) -> int:
    """码 -> 文件坐标 (÷2025.37×100000)"""
    return int(round(yards / YARDS_PER_NMI * NMI_SCALE))

def calc_offset(bearing_deg: float, dist_nmi: float):
    """罗盘方位(0=北顺时针, Y 向北为正) + 海里距离 -> (dx, dy) 文件单位"""
    rad = math.radians(bearing_deg)
    return nm_to_file(dist_nmi * math.sin(rad)), nm_to_file(dist_nmi * math.cos(rad))

def offset_yards(bearing_deg: float, yards: float):
    """罗盘方位 + 码 -> (dx, dy) 文件单位"""
    d = yard_to_file(yards)
    rad = math.radians(bearing_deg)
    return int(round(d * math.sin(rad))), int(round(d * math.cos(rad)))

# ---------- 单位构造 ----------
def mk_unit(uid, side, track, name, uclass, utype, x, y, course, speed,
            scn_time, del_time='2020-01-01 00:00:00',
            tag_course_speed=True):
    """构造一个标准水面单位 dict
    uid: 'S001' (S=水面/A=飞机/U=潜艇/L=岸上)
    uclass: 'BB'/'CL'/'CA'/'DD'... | utype: 'battleship'/'cruiser'/'destroyer'...
    course/speed: 度数/节 (内部自动 ×1000)
    tag_course_speed=True -> 标签显示 名称+航向航速 (玩家常用)
    """
    return {
        "IdNum": uid, "Side": side, "TrackNumber": track, "Name": name,
        "Number": 1, "UnitClass": uclass, "UnitType": utype,
        "X": x, "Y": y, "ShowSunk": False, "IsActiveRadar": False, "IsActiveSonar": False,
        "PositionTimeCreated": scn_time, "PositionTimeDeleted": del_time,
        "Speed": int(speed * 1000), "Course": int(course * 1000),
        "Range": -100000, "WpDistance": 0,
        "PastWaypointArray1": {}, "FutureWaypointArray1": {},
        "TextTags": {"TagAltitude": False, "TagCallsign": False, "TagClass": False,
                     "TagCourseSpeed": tag_course_speed, "TagDepth": False, "TagName": True,
                     "TagTrackNum": False, "TagUnitType": False, "AdditionalText": ""},
    }

# ---------- 飞机生命周期 (未起飞不建单位, 起飞新建/降落移除) ----------
def mk_air_unit(uid, side, track, name, uclass, utype, x, y, course, speed,
                altitude, scn_time, del_time='2020-01-01 00:00:00',
                tag_course_speed=True) -> dict:
    """构造飞机单位 dict = mk_unit 全部字段 + Altitude(米×1000)
    course/speed/altitude: 度数/节/米 (内部自动 ×1000)
    track 传 None 时由 add_unit() 自动分配 (Scenario.CurrentTrackNumber 自增)
    """
    u = mk_unit(uid, side, track, name, uclass, utype, x, y, course, speed,
                scn_time, del_time=del_time, tag_course_speed=tag_course_speed)
    u['Altitude'] = int(altitude * 1000)
    return u


def add_unit(data, unit) -> None:
    """新建单位入档: Units.append + Objects.append
    - TrackNumber: 若 unit 未给/为 None, 取 Scenario.CurrentTrackNumber 并自增 1
    - LastId: 更新为所有 IdNum 数字后缀最大值 (前缀 S/A/U/L 统一取最大)
    """
    if unit.get('TrackNumber') is None:
        scn = data.setdefault('Scenario', {})
        unit['TrackNumber'] = scn.get('CurrentTrackNumber', 0)
        scn['CurrentTrackNumber'] = unit['TrackNumber'] + 1
    data.setdefault('Units', []).append(unit)
    data.setdefault('Objects', []).append(unit['IdNum'])
    # LastId = 全部单位 IdNum 数字后缀最大值 (与现有 LastId 取大, 避免删除单位后回退)
    m = 0
    for u in data.get('Units', []):
        s = u.get('IdNum', '') if isinstance(u, dict) else ''
        if s and s[0] in 'SAUL':
            try:
                m = max(m, int(s[1:]))
            except (ValueError, IndexError):
                pass
    scn = data.setdefault('Scenario', {})
    scn['LastId'] = max(m, scn.get('LastId', 0))


def remove_unit(data, idnum) -> None:
    """移除单位: 从 Units 与 Objects 中删除 (不回收 TrackNumber/IdNum) """
    data['Units'] = [u for u in data.get('Units', []) if u.get('IdNum') != idnum]
    data['Objects'] = [o for o in data.get('Objects', []) if o != idnum]


def find_unit(data, idnum_or_name):
    """按 IdNum/Name 在 Units 中查找单位 (IdNum 精确优先, 无则 Name 精确/包含匹配), 找不到返回 None"""
    for u in data.get('Units', []):
        if u.get('IdNum') == idnum_or_name:
            return u
    for u in data.get('Units', []):
        nm = u.get('Name', '')
        if nm and (nm == idnum_or_name or idnum_or_name in nm or nm in idnum_or_name):
            return u
    return None


# ---------- 存档状态识别 (Do 前 / Do 后 / Do+Next) ----------
def detect_state(data: dict) -> str:
    """识别存档操作状态 (Phase 语义: 0=plotting, 2=post-movement):
    - 'do_before': 未点 Do (TurnTime==PositionTime 且无轨迹点, Phase=0) —— 初始/规划
    - 'do_after' : 已点 Do 未点 Next (TurnTime != PositionTime, Phase=2) —— 移动后阶段
    - 'do_next'  : Do+Next 已确认 (TurnTime==PositionTime 且有轨迹点, Phase 回到 0)
    """
    tt = data['Time']['CurrentTurnTime']
    pt = data['Time']['CurrentPositionTime']
    has_wp = any(len(u.get('PastWaypointArray1', [])) > 0 for u in data['Units'])
    if tt == pt:
        return 'do_next' if has_wp else 'do_before'
    return 'do_after'

def state_label(s: str) -> str:
    """状态中文描述"""
    return {'do_before': 'Do 前 (初始, 时间未动)',
            'do_after': 'Do 后 (已移动, 未 Next, 时间待确认)',
            'do_next': 'Do+Next (回合已确认)'}.get(s, s)

# ---------- 单位移动 (简单直行模型, 无前冲转向) ----------
def _alt_depth(u):
    if 'Altitude' in u:
        return u['Altitude']
    if 'Depth' in u:
        return u['Depth']
    return 0

def _make_waypoint(u, ts):
    return ["", u['X'], u['Y'], 0, 0, _alt_depth(u), 0, 0, 0, 1, True, ts]

def move_units(data, minutes, course_delta_deg=0.0, speed_delta_knots=0.0,
               scenario_name=None, phase=2, preserve_state=True):
    """移动所有单位, 记录轨迹, 按原状态推进时间 (状态保持)
    - 记录移动前位置到 PastWaypointArray1 (轨迹点)
    - 按 course_delta_deg/speed_delta_knots 应用机动 (简单直行)
    - 状态保持: do_before/do_after -> TurnTime 不变, Phase=2 (结果 do_after)
                do_next         -> TurnTime 同步推进, Phase 保持 0 (结果仍 do_next)
    """
    d = copy.deepcopy(data)
    state = detect_state(d)
    hours = minutes / 60.0
    cur_time = d['Time']['CurrentPositionTime']
    for u in d['Units']:
        past = u.get('PastWaypointArray1')
        if not isinstance(past, list):
            past = []
        past.append(_make_waypoint(u, cur_time))
        u['PastWaypointArray1'] = past
        speed_knots = u['Speed'] / 1000.0 + speed_delta_knots
        course_deg = (u['Course'] / 1000.0 + course_delta_deg) % 360.0
        dist_nmi = speed_knots * hours
        rad = math.radians(course_deg)
        u['X'] += int(round(dist_nmi * math.sin(rad) * NMI_SCALE))
        u['Y'] += int(round(dist_nmi * math.cos(rad) * NMI_SCALE))
        if speed_delta_knots != 0.0:
            u['Speed'] = int(round(speed_knots * 1000))
        if course_delta_deg != 0.0:
            u['Course'] = int(round(course_deg * 1000))
    # 时间推进 (状态保持)
    fmt = '%Y-%m-%d %H:%M:%S'
    pt_s = (datetime.datetime.strptime(cur_time, fmt) + datetime.timedelta(minutes=minutes)).strftime(fmt)
    d['Time']['CurrentPositionTime'] = pt_s
    if preserve_state and state == 'do_next':
        d['Time']['CurrentTurnTime'] = pt_s
        turns = d.get('Turns')
        if isinstance(turns, list):
            new_turn = {'TurnTime': pt_s, 'TurnInterval': {'Minutes': 3, 'Seconds': 0}}
            if not any(isinstance(x, dict) and x.get('TurnTime') == pt_s for x in turns):
                turns.append(new_turn)
            d['Turns'] = turns
        d['Scenario']['Phase'] = 0
    else:
        d['Scenario']['Phase'] = 2 if preserve_state else phase
    if scenario_name:
        d['Scenario']['ScenarioName'] = scenario_name
    return d

# ---------- 剧本推演命令表 ----------
def _is_sub(u):
    """潜艇: 有 Depth 字段"""
    return 'Depth' in u

def _is_air(u):
    """飞机: 有 Altitude 字段"""
    return 'Altitude' in u

SIDE_CN = {'Blue': '蓝方 Blue', 'Red': '红方 Red', 'Neutral': '中立 Neutral'}
STATE_CN = {'do_before': '初始（Do 前）', 'do_after': 'Do 后（未 Next）', 'do_next': 'Next 后（已确认）'}

def write_cmd_sheet(scn_path: str, out_dir: str = None, weather: dict = None,
                   aircraft: list = None) -> str:
    """根据剧本初设存档生成剧本推演命令表 (规则: 剧本名+初设)
    - 顶部: 剧本基本信息(名称/回合时间/回合时长/状态) + 天气海况(可选参数 weather)
    - 按阵营(Blue/Red/Neutral)分组, 每组内分水面舰艇/潜艇/飞机表
    - 尺寸 / 最大速度: 留空 (玩家填写); 计划列: 留空
    - aircraft: 可选, 未起飞飞机清单 (list of dict, 由 AI 从剧本说明维护, 不写入存档):
        {IdNum, Side, Name, UnitClass, UnitType, MaxSpeed, HomeIdNum, HomeName}
      飞机表 = 已起飞(存档 Units 中带 Altitude 的单位) ∪ 未起飞(aircraft 清单);
      未起飞行当前状态=未起飞、当前速度/航向/高度=—、最大速度预填, 供玩家填计划状态(起飞/降落)
    weather 示例: {'sea_state': 3, 'wind_dir': '东南', 'wind_speed': '13节',
                   'visibility': '100%', 'sunrise': '05:56'}
    返回输出文件路径
    """
    d = load_scenario(scn_path)
    name = d['Scenario']['ScenarioName']
    out_dir = out_dir or os.path.dirname(scn_path)
    out = os.path.join(out_dir, '剧本推演命令表-%s初设.md' % name)
    lines = ['# 剧本推演命令表 - %s' % name, '']
    aircraft = aircraft or []
    aircraft_by_id = {e.get('IdNum'): e for e in aircraft if isinstance(e, dict)}

    # ---- 剧本基本信息 ----
    t = d['Time']
    tt, pt = t['CurrentTurnTime'], t['CurrentPositionTime']
    mins = t.get('CurrentTurnInterval', {}).get('Minutes', 3)
    turn_label = '中继回合（%d 分钟）' % mins if mins >= 30 else '战术回合（%d 分钟）' % mins
    state = STATE_CN.get(detect_state(d), '')
    lines += ['## 剧本信息', '',
              '| 剧本名称 | 当前回合时间 | 当前位置时间 | 回合时长 | 状态 |',
              '| --- | --- | --- | --- | --- |',
              '| %s | %s | %s | %s | %s |' % (name, tt, pt, turn_label, state), '']

    # ---- 天气海况 (可选) ----
    if weather:
        lines += ['## 天气海况', '',
                  '| 海况 | 风向 | 风速 | 能见度 | 日出时间 |',
                  '| --- | --- | --- | --- | --- |',
                  '| %s | %s | %s | %s | %s |' % (
                      weather.get('sea_state', ''), weather.get('wind_dir', ''),
                      weather.get('wind_speed', ''), weather.get('visibility', ''),
                      weather.get('sunrise', '')), '']

    # ---- 按阵营分组 ----
    for side, side_cn in SIDE_CN.items():
        side_units = [u for u in d['Units'] if u.get('Side') == side]
        aircraft_side = [e for e in aircraft if e.get('Side') == side]
        # 阵营跳过条件纳入未起飞飞机: 纯飞机阵营 (无 Units 单位) 也输出 (至少飞机表)
        if not side_units and not aircraft_side:
            continue
        subs = [u for u in side_units if _is_sub(u)]
        airs = [u for u in side_units if _is_air(u)]
        ships = [u for u in side_units if not _is_sub(u) and not _is_air(u)]
        lines.append('## %s（共 %d 个单位）' % (side_cn, len(side_units) + len(aircraft_side)))
        lines.append('')
        # 水面舰艇表
        if ships:
            lines += ['### 水面舰艇',
                      '',
                      '| 舰船名称 | 尺寸 | 最大速度 | 当前速度 | 当前航向 | 计划航速 | 计划航向 |',
                      '| --- | --- | --- | --- | --- | --- | --- |']
            for u in ships:
                nm = u.get('Name', u['IdNum'])
                lines.append('| %s |  |  | %d | %d |  |  |' % (nm, u['Speed'] // 1000, u['Course'] // 1000))
            lines.append('')
        # 潜艇表 (状态=水上/静航/非静航; 深度>0 默认静航)
        if subs:
            lines += ['### 潜艇',
                      '',
                      '| 潜艇名称 | 尺寸 | 最大速度 | 当前状态 | 当前速度 | 当前航向 | 当前深度 | 计划状态 | 计划航向 | 计划速度 | 计划深度 |',
                      '| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |']
            for u in subs:
                nm = u.get('Name', u['IdNum'])
                depth = u.get('Depth', 0) // 1000
                st = '静航' if depth > 0 else '水上'
                lines.append('| %s |  |  | %s | %d | %d | %d |  |  |  |  |' % (
                    nm, st, u['Speed'] // 1000, u['Course'] // 1000, depth))
            lines.append('')
        # 飞机表 (生命周期: 已起飞 Units 单位 ∪ 未起飞 aircraft 清单; 状态改变按玩家指令, 无校验)
        if airs or aircraft_side:
            # 行来源 = 已起飞(Units) ∪ 未起飞(aircraft), 按 IdNum 排序合并
            rows = {}
            for u in airs:
                rows[u.get('IdNum', '')] = ('air', u)
            for e in aircraft_side:
                rows.setdefault(e.get('IdNum', ''), ('aircraft', e))
            lines += ['### 飞机',
                      '',
                      '| 飞机名称 | 所属母舰/基地 | 尺寸 | 最大速度 | 当前状态 | 当前速度 | 当前航向 | 当前高度 | 计划状态 | 计划航向 | 计划速度 | 计划高度 |',
                      '| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |']
            for idnum in sorted(rows.keys()):
                kind, item = rows[idnum]
                nm = item.get('Name', idnum)
                if kind == 'air':
                    # 已起飞: 当前列=实际值; 所属母舰/基地 = aircraft 匹配项(按 IdNum)或空
                    alt = item.get('Altitude', 0) // 1000
                    home = aircraft_by_id.get(idnum, {}).get('HomeName', '')
                    lines.append('| %s | %s |  |  | 飞行中 | %d | %d | %d |  |  |  |  |' % (
                        nm, home, item['Speed'] // 1000, item['Course'] // 1000, alt))
                else:
                    # 未起飞: 当前速度/航向/高度=—, 最大速度预填 (可改)
                    lines.append('| %s | %s |  | %s | 未起飞 | — | — | — |  |  |  |  |' % (
                        nm, item.get('HomeName', ''), item.get('MaxSpeed') or ''))
            lines.append('')

    open(out, 'w', encoding='utf-8').write('\n'.join(lines))
    return out

# 兼容别名 (旧名)
write_initial_sheet = write_cmd_sheet

# ---------- 输出命名 ----------
def output_name(base: str, pos_time: str) -> str:
    """存档名 + PositionTime -> 文件名主体 (如 123-2026-08-04-22-06-00)"""
    return '%s-%s' % (base, pos_time.replace(':', '-').replace(' ', '-'))

def write_turn_result(base_dir: str, src_file: str, data: dict, scenario_name: str = None) -> str:
    """推进回合后输出新存档: <存档名>-<PositionTime>.json (不覆盖旧档)"""
    base = src_file[:-5] if src_file.lower().endswith('.json') else src_file
    if src_file.lower().endswith('.json'):
        base = src_file[:-5]
    elif src_file.lower().endswith('.spscn'):
        base = src_file[:-6]
    new_name = output_name(base, data['Time']['CurrentPositionTime'])
    if scenario_name:
        data['Scenario']['ScenarioName'] = scenario_name
    out = os.path.join(base_dir, new_name + '.json')
    write_json(out, data)
    return out
