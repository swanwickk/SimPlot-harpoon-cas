"""
SimPlot2 自然语言指令系统 (鱼叉规则)
将自然语言推进回合命令 -> 新存档 (不覆盖旧存档)

核心规则 (Harpoon V 同步回合):
- 所有速度>0 的单位按 回合时长x航速 沿当前航向移动
- 指定单位应用新参数 (航向/航速/高度/深度), 未指定维度保持当前值
- 回合时长: 显式"X分钟" > 中继回合(30min) > 战术回合/默认(3min)
- 尺寸等级: 慢速A/快速A/B/C/D (加速分两列: 0-75%/75-100% 最大航速)
- 转向: <=10°免前冲; >10° 前冲+分段(单次45°); 渐进式(距离不足部分转向, 0距离不转向)
- 转向>=45°加速减半; 每45°转向损失航速; 急舵须命令明确提及
- 状态保持: 按原存档状态 (do_after/do_next) 推进
- 输出命名: <存档名>-<PositionTime 紧凑格式>.json
"""
import sys, os, re, json, math, copy, datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from scn_tool import (read_scn, write_scn, detect_state, move_units, NMI_SCALE, write_json)

# ================= 1. 自然语言解析 =================
RELAY_MINUTES = 30
TACTICAL_MINUTES = 3

def parse_command(text: str) -> dict:
    """解析回合时长, 返回 {'minutes': float|None}"""
    cmd = {'minutes': None}
    m = re.search(r'(\d+(?:\.\d+)?)\s*(?:分钟|min)', text, re.I)
    if m:
        cmd['minutes'] = float(m.group(1))
    elif re.search(r'中继回合', text):
        cmd['minutes'] = RELAY_MINUTES
    elif re.search(r'(?:一个|1个)?(?:战术)?回合', text):
        cmd['minutes'] = TACTICAL_MINUTES
    return cmd

def parse_unit_updates(text: str, unit) -> dict:
    """解析单个单位的参数更新 (不含全局提速, 由 process 处理)"""
    upd = {}

    # 航向: "航向XXX" / "转向X度" / "右转X" / "左转X"
    m = re.search(r'航向\s*(\d{1,3})', text)
    if m:
        upd['course'] = float(m.group(1))
    else:
        m = re.search(r'右转\s*(\d{1,3})', text)
        if m:
            upd['course_delta'] = float(m.group(1))
        else:
            m = re.search(r'左转\s*(\d{1,3})', text)
            if m:
                upd['course_delta'] = -float(m.group(1))
            else:
                m = re.search(r'转向\s*(\d{1,3})', text)
                if m:
                    upd['course'] = float(m.group(1))

    # 航速(带数值): "加速X节" / "减速X节" / "X节"
    m = re.search(r'加速\s*(\d+(?:\.\d+)?)\s*节', text)
    if m:
        upd['speed_delta'] = float(m.group(1))
    else:
        m = re.search(r'减速\s*(\d+(?:\.\d+)?)\s*节', text)
        if m:
            upd['speed_delta'] = -float(m.group(1))
        else:
            m = re.search(r'(\d+(?:\.\d+)?)\s*节', text)
            if m:
                upd['speed'] = float(m.group(1))

    # 高度 (飞机): "高度X米" / "爬升到X米" / "X米高度"
    m = re.search(r'(?:高度|爬升到|下降至?到?|升到)\s*(\d+(?:\.\d+)?)\s*米', text)
    if m:
        upd['altitude'] = float(m.group(1))

    # 深度 (潜艇): "深度X米" / "下潜到X米" / "上浮到X米"
    m = re.search(r'(?:深度|下潜到|上浮到)\s*(\d+(?:\.\d+)?)\s*米', text)
    if m:
        upd['depth'] = float(m.group(1))

    return upd

# ================= 2. 单位匹配 =================
# 尺寸等级完整配置 (无调距桨):
#   accel=0-75%最大航速时加速 / accel_high=75-100%时加速 / decel=减速
#   adv=标准舵前冲(码) / loss=标准舵每45°损失(节) / adv_emerg=急舵前冲 / loss_emerg=急舵每45°损失
SIZE_LEVELS = {
    'slowA': dict(accel=4,  accel_high=2, decel=6,  adv=400, loss=2, adv_emerg=300, loss_emerg=3),
    'fastA': dict(accel=6,  accel_high=3, decel=9,  adv=400, loss=2, adv_emerg=300, loss_emerg=3),
    'B':     dict(accel=10, accel_high=5, decel=12, adv=300, loss=2, adv_emerg=200, loss_emerg=3),
    'C':     dict(accel=12, accel_high=6, decel=15, adv=300, loss=1, adv_emerg=200, loss_emerg=2),
    'D':     dict(accel=12, accel_high=6, decel=15, adv=200, loss=2, adv_emerg=100, loss_emerg=1),
}
# UnitClass -> 尺寸级 默认映射 (剧本相关, 不固定, 可按剧本调整)
# 'A' 为通用A级, 按最大航速判定快/慢: >=25节=快速A, <25节=慢速A; 无最大航速信息默认快速A
CLASS_SIZE = {'BB': 'A', 'BC': 'A', 'CL': 'B', 'CA': 'B', 'CC': 'B',
              'CV': 'B', 'DD': 'C', 'FF': 'C'}
FAST_A_MIN_SPEED = 25.0  # 最大航速达到25节 -> 快速A
# 单位最大航速(节) 剧本配置 (用于 A级快/慢判定与 75% 加速阈值); 也可由舰船信息表/命令指定
UNIT_MAX_SPEED = {}
UNIT_ALIASES = {'莫加多尔': '莫多加尔'}  # 译名别名
# 水下潜艇固定转向参数 (不随尺寸等级): 标准舵前冲300码/损失1节, 急舵200码/损失2节
SUB_ADV_YARDS = 300.0
SUB_ADV_EMERG_YARDS = 200.0
SUB_LOSS_KNOTS = 1.0
SUB_LOSS_EMERG_KNOTS = 2.0
# 静航状态加减速能力为正常的 50% (新建潜艇有深度默认静航)
SUB_SILENT_ACCEL_FACTOR = 0.5

def _is_submerged(unit) -> bool:
    """是否水下潜艇 (有 Depth 字段且深度>0)"""
    return unit.get('Depth', 0) > 0

def _unit_max_speed(unit):
    return UNIT_MAX_SPEED.get(unit.get('IdNum')) or UNIT_MAX_SPEED.get(unit.get('Name', ''))

def _resolve_size(unit) -> str:
    """解析单位尺寸级; A级按最大航速判定快/慢"""
    lv = CLASS_SIZE.get(unit.get('UnitClass', ''), 'B')
    if lv == 'A':
        ms = _unit_max_speed(unit)
        return 'fastA' if (ms is None or ms >= FAST_A_MIN_SPEED) else 'slowA'
    return lv

def accel_capability(unit, current_speed_knots=None) -> float:
    """按尺寸等级与当前航速(相对最大航速)返回加速能力(节)
    当前航速 > 最大航速×75% 时用第二列(减半档)
    水下潜艇默认静航: 加减速能力为正常的 50%
    """
    lv = SIZE_LEVELS[_resolve_size(unit)]
    ms = _unit_max_speed(unit)
    accel = float(lv['accel_high']) if (ms and current_speed_knots is not None
                                        and current_speed_knots > ms * 0.75) else float(lv['accel'])
    if _is_submerged(unit):
        accel *= SUB_SILENT_ACCEL_FACTOR  # 静航 50%
    return accel

def _advance_yards(unit, emergency: bool = False) -> float:
    """单位单次45°转向前冲距离(码); 急舵用急舵列
    水下潜艇固定: 标准舵300码 / 急舵200码 (不随尺寸等级)
    """
    if _is_submerged(unit):
        return SUB_ADV_EMERG_YARDS if emergency else SUB_ADV_YARDS
    lv = SIZE_LEVELS[_resolve_size(unit)]
    return float(lv['adv_emerg'] if emergency else lv['adv'])

def _turn_loss_knots(unit, emergency: bool = False) -> float:
    """单位每转45°的航速损失(节); 急舵用急舵列
    水下潜艇固定: 标准舵1节 / 急舵2节 (不随尺寸等级)
    """
    if _is_submerged(unit):
        return SUB_LOSS_EMERG_KNOTS if emergency else SUB_LOSS_KNOTS
    lv = SIZE_LEVELS[_resolve_size(unit)]
    return float(lv['loss_emerg'] if emergency else lv['loss'])

def match_unit(u, target: str) -> bool:
    """按 Name / IdNum 匹配单位 (含别名, Name 为空时避免空串误匹配)"""
    name = u.get('Name', '')
    uid = u.get('IdNum', '')
    if target == '*':
        return True
    if name and (target in name or name in target):
        return True
    if name and target in UNIT_ALIASES and UNIT_ALIASES[target] == name:
        return True
    return target.upper() == uid.upper()

def _unit_in_text(u, text: str) -> bool:
    """文本中是否提及该单位 (全名/别名/前2字简称/IdNum)"""
    nm = u.get('Name', '')
    uid = u.get('IdNum', '')
    if uid and uid in text:
        return True
    if not nm:
        return False
    if nm in text:
        return True
    for a, canon in UNIT_ALIASES.items():
        if canon == nm and a in text:
            return True
    if len(nm) >= 3 and nm[:2] in text:
        return True
    return False

def find_unit_word(u, text: str) -> str:
    """返回该单位在文本中的实际用词 (全名/别名/简称/IdNum)"""
    nm = u.get('Name', '')
    uid = u.get('IdNum', '')
    if nm and nm in text:
        return nm
    if nm:
        for a, canon in UNIT_ALIASES.items():
            if canon == nm and a in text:
                return a
    if len(nm or '') >= 3 and nm[:2] in text:
        return nm[:2]
    return uid if uid in text else None

def extract_segment(text: str, word: str, all_words: list) -> str:
    """提取单位名之后的指令段 (截断到下一个单位名)"""
    idx = text.find(word)
    if idx == -1:
        return ''
    seg = text[idx + len(word):]
    cut = len(seg)
    for w in all_words:
        if w == word or not w:
            continue
        j = seg.find(w)
        if j != -1 and j < cut:
            cut = j
    return seg[:cut]

# ================= 3. 执行推进 =================
# 转向角度 <=10° 无需前冲 (直接转向)
NO_ADVANCE_DEG = 10.0

def _turn_count(delta_deg) -> int:
    """转向角(带符号) -> 45°转向次数"""
    return max(1, int(math.ceil(abs(delta_deg) / 45))) if abs(delta_deg) >= 0.5 else 0

def _turn_motion(x, y, old_course, new_course, dist_file, advance_file):
    """带前冲的转向运动 (渐进式):
    - 0距离: 不移动不转向 (航向保持 old_course)
    - 转向 <=10°: 无需前冲, 直接沿新航向移动全程 (轨迹无中间点)
    - 转向 >10°: 逐段执行"前冲 advance_file + 转45°" (单次最多45°);
      当剩余距离不足以完成下一次前冲时, 沿当前航向走完剩余距离,
      转向角度停在已完成部分 (实际航向 < 计划航向)
    返回 (新X, 新Y, 转向点列表[(x,y),...], 实际最终航向)
    """
    if new_course is None:
        new_course = old_course
    delta = (new_course - old_course) % 360
    if delta > 180:
        delta -= 360
    if dist_file <= 0:
        return x, y, [], old_course  # 0距离: 无法前冲, 无法转向
    if abs(delta) <= NO_ADVANCE_DEG:
        dx = dist_file * math.sin(math.radians(new_course))
        dy = dist_file * math.cos(math.radians(new_course))
        return int(x + dx), int(y + dy), [], new_course
    n = max(1, int(math.ceil(abs(delta) / 45)))
    step = 45 if delta > 0 else -45
    cx, cy = x, y
    remaining = dist_file
    cur = old_course
    points = []
    for i in range(n):
        if remaining < advance_file:
            # 距离不足以完成下一次前冲: 沿当前航向走完剩余, 不再转向
            dx = remaining * math.sin(math.radians(cur))
            dy = remaining * math.cos(math.radians(cur))
            return int(cx + dx), int(cy + dy), points, cur
        dx = advance_file * math.sin(math.radians(cur))
        dy = advance_file * math.cos(math.radians(cur))
        cx += dx
        cy += dy
        points.append((int(cx), int(cy)))
        remaining -= advance_file
        cur = (cur + step) % 360
    # 全部前冲完成, 剩余沿最终航向走
    dx = remaining * math.sin(math.radians(new_course))
    dy = remaining * math.cos(math.radians(new_course))
    return int(cx + dx), int(cy + dy), points, new_course

def advance_scenario(data: dict, cmd: dict) -> dict:
    """执行推进: 移动所有单位(含渐进式前冲转向), 应用指定参数, 时间推进, 状态保持"""
    d = copy.deepcopy(data)
    state = detect_state(d)
    minutes = cmd.get('minutes') or d['Time']['CurrentTurnInterval'].get('Minutes', 3)
    cur_time = d['Time']['CurrentPositionTime']
    hours = minutes / 60.0
    emergency = bool(cmd.get('emergency', False))  # 急舵

    updates = cmd.get('units', {})
    for u in d['Units']:
        upd = updates.get(u['IdNum'], {})
        old_course = u['Course'] / 1000.0
        old_speed = u['Speed'] / 1000.0

        # 计算新航向
        new_course = old_course
        if 'course' in upd:
            new_course = float(upd['course'])
        if 'course_delta' in upd:
            new_course = (old_course + float(upd['course_delta'])) % 360.0

        # 计算新航速: 原速 + 加速(转向>=45°减半) - 转向航速损失(每45°按表)
        delta = (new_course - old_course) % 360
        if delta > 180:
            delta -= 360
        n_turn = _turn_count(delta)
        turn_loss = n_turn * _turn_loss_knots(u, emergency)
        new_speed = old_speed
        if 'speed' in upd:
            new_speed = float(upd['speed'])
        if 'speed_delta' in upd:
            accel = float(upd['speed_delta'])
            if accel > 0 and abs(delta) >= 45:
                accel /= 2.0  # 转向45°+ 加速率减半
            new_speed = old_speed + accel
        new_speed -= turn_loss  # 转向航速损失
        new_speed = max(0.0, new_speed)

        # 高度/深度
        if 'altitude' in upd and 'Altitude' in u:
            u['Altitude'] = int(round(float(upd['altitude']) * 1000))
        if 'depth' in upd and 'Depth' in u:
            u['Depth'] = int(round(float(upd['depth']) * 1000))

        # 记录起点轨迹 (移动前位置)
        past = u.get('PastWaypointArray1')
        if not isinstance(past, list):
            past = []
        alt = u.get('Altitude', u.get('Depth', 0))
        past.append(["", u['X'], u['Y'], 0, 0, alt, 0, 0, 0, 1, True, cur_time])

        # 移动 (前冲转向: 按尺寸等级标准舵; 急舵用急舵列; 转向<=10°无前冲; 0距离不转向)
        dist_file = new_speed * hours * NMI_SCALE
        if new_speed <= 0 or dist_file <= 0:
            nx, ny, turn_pts, actual_course = u['X'], u['Y'], [], old_course
        else:
            adv = _advance_yards(u, emergency) * NMI_SCALE / 2025.37
            nx, ny, turn_pts, actual_course = _turn_motion(u['X'], u['Y'], old_course, new_course, dist_file, adv)

        # 转向点加入轨迹
        for px, py in turn_pts:
            past.append(["", px, py, 0, 0, alt, 0, 0, 0, 1, True, cur_time])

        u['X'], u['Y'] = nx, ny
        u['Course'] = int(round(actual_course * 1000))  # 实际完成转向后的航向
        u['Speed'] = int(round(new_speed * 1000))
        u['PastWaypointArray1'] = past

    # 时间推进 (状态保持)
    fmt = '%Y-%m-%d %H:%M:%S'
    pt = datetime.datetime.strptime(cur_time, fmt) + datetime.timedelta(minutes=minutes)
    pt_s = pt.strftime(fmt)
    d['Time']['CurrentPositionTime'] = pt_s
    d['Time']['CurrentTurnInterval'] = {'Minutes': int(minutes), 'Seconds': 0}
    if state == 'do_next':
        d['Time']['CurrentTurnTime'] = pt_s
        turns = d.get('Turns')
        if isinstance(turns, list):
            nt = {'TurnTime': pt_s, 'TurnInterval': {'Minutes': int(minutes), 'Seconds': 0}}
            if not any(isinstance(x, dict) and x.get('TurnTime') == pt_s for x in turns):
                turns.append(nt)
        d['Scenario']['Phase'] = 0
    else:
        d['Scenario']['Phase'] = 2
    return d

def output_name(base: str, pos_time: str) -> str:
    """存档名 + PositionTime -> 文件名主体"""
    return '%s-%s' % (base, pos_time.replace(':', '-').replace(' ', '-'))

# ================= 4. 主流程 =================
def process(base_dir: str, src_file: str, text: str) -> tuple:
    """读存档 -> 解析指令 -> 推进 -> 输出新存档, 返回 (输出路径, 新数据)
    base_dir: Scenarios 目录路径; src_file: 存档文件名; text: 自然语言指令
    """
    src_path = os.path.join(base_dir, src_file)
    data = json.loads(open(src_path, 'rb').read().decode('utf-8'))

    cmd = parse_command(text)
    updates = {}

    # 急舵: 命令明确提到"急舵" -> 转向单位用急舵(前冲-100码, 损失按急舵列)
    cmd['emergency'] = '急舵' in text

    # 全局"提速/加速"无数值 -> 所有单位按尺寸等级能力加速 (叠加到各单位)
    has_global_accel = bool(re.search(r'提速|加速', text)) and not re.search(
        r'(?:加速|提速)\s*(\d+(?:\.\d+)?)\s*节', text)

    # 识别文本中提及的单位 (Name/别名/IdNum)
    mentioned = [u for u in data['Units'] if _unit_in_text(u, text)]

    # 构建全部单位用词 (用于分段截断: 全名/别名/简称/IdNum)
    all_words = []
    for u in data['Units']:
        nm = u.get('Name', '')
        if nm:
            all_words.append(nm)
            if len(nm) >= 3:
                all_words.append(nm[:2])
            for a, canon in UNIT_ALIASES.items():
                if canon == nm:
                    all_words.append(a)
        all_words.append(u.get('IdNum', ''))
    all_words = list(dict.fromkeys(w for w in all_words if w))

    # 具体单位指令: 按单位分段解析
    for u in mentioned:
        word = find_unit_word(u, text)
        if word:
            seg = extract_segment(text, word, all_words)
            updates[u['IdNum']] = parse_unit_updates(seg, u)

    # 全局提速叠加 (所有单位按尺寸等级能力加速; 按当前航速选 75% 档)
    if has_global_accel:
        for u in data['Units']:
            upd = updates.get(u['IdNum'], {})
            upd['speed_delta'] = accel_capability(u, u['Speed'] / 1000.0)
            updates[u['IdNum']] = upd

    # 无任何指令 -> 全部直行
    if not updates:
        updates['*'] = {}
    cmd['units'] = updates

    # 执行
    new_data = advance_scenario(data, cmd)

    # 输出命名: 存档名 + PositionTime (不覆盖旧档)
    base = src_file[:-5] if src_file.endswith('.json') else src_file
    new_name = output_name(base, new_data['Time']['CurrentPositionTime'])
    new_data['Scenario']['ScenarioName'] = new_name
    out_path = os.path.join(base_dir, new_name + '.json')
    write_json(out_path, new_data)
    return out_path, new_data
