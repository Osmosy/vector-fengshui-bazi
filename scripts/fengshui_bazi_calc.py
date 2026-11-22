#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fengshui_bazi_calc.py — детерминированные расчёты навыка fengshui-bazi.

Только стандартная библиотека Python 3.8+, без pip-зависимостей.

Команды:
  pillars      — четыре столпа бацзы + скрытые стволы + 十神 + найнь + 大运
  gua          — число гуа (八宅) и 8 направлений жизни
  feixing      — карта летящих звёзд (下卦) по фасаду и году заселения
  numerology   — числа западной нумерологии + психоматрица Пифагора
  match        — балльная совместимость пары (八字合婚, веса yinyuan-skills)
  zodiac       — быстрая зодиакальная совместимость (生肖)

Калибры: год — по 立春, месяц — по 12 节, день — смена в 23:00
(флаг --yeci: 23:00–24:00 остаётся текущим днём). Солнечная долгота —
формула низкой точности Meeus (±0.01°, время ±15–20 минут).
Гарантированный диапазон дат: 1900–2100.

Якоря (проверено): 1990-05-15 = 庚辰-день; 1893-12-26 = 丁酉-день;
1977-09-23 19:00 (UTC+8) = 丁巳 己酉 癸未 壬戌; 1984 м → гуа 7, 1990 м → 1.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import date, datetime, timedelta, timezone

UTC = timezone.utc
J2000 = datetime(2000, 1, 1, 12, 0, 0, tzinfo=UTC)
JDN_OFFSET = 1721425  # JDN = date.toordinal() + 1721425

GAN = "甲乙丙丁戊己庚辛壬癸"
ZHI = "子丑寅卯辰巳午未申酉戌亥"
GAN_RU = ["Цзя", "И", "Бин", "Дин", "У", "Цзи", "Гэн", "Синь", "Жэнь", "Гуй"]
ZHI_RU = ["Цзы", "Чоу", "Инь", "Мао", "Чэнь", "Сы", "У", "Вэй",
          "Шэнь", "Ю", "Сюй", "Хай"]
GAN_EL = ["Дерево", "Дерево", "Огонь", "Огонь", "Земля",
          "Земля", "Металл", "Металл", "Вода", "Вода"]
BR_EL = ["Вода", "Земля", "Дерево", "Дерево", "Земля", "Огонь",
         "Огонь", "Земля", "Металл", "Металл", "Земля", "Вода"]
ZH_RU = ["Крыса", "Бык", "Тигр", "Кролик", "Дракон", "Змея",
         "Лошадь", "Коза", "Обезьяна", "Петух", "Собака", "Свинья"]
HIDDEN = [[9], [5, 7, 9], [0, 2, 4], [1], [4, 1, 9], [2, 4, 6], [3, 5],
          [5, 3, 1], [6, 8, 4], [7], [4, 7, 3], [8, 0]]

# 纳音 (найнь): 30 пар шестидесятерицы, (иероглифы, перевод, стихия)
NAYIN = [
    ("海中金", "Металл в море", "Металл"), ("炉中火", "Огонь в печи", "Огонь"),
    ("大林木", "Большой лес", "Дерево"), ("路旁土", "Земля у дороги", "Земля"),
    ("剑锋金", "Металл клинка", "Металл"), ("山头火", "Огонь на вершине", "Огонь"),
    ("涧下水", "Вода ручья", "Вода"), ("城墙土", "Земля городской стены", "Земля"),
    ("白蜡金", "Металл белого воска", "Металл"), ("杨柳木", "Дерево ивы", "Дерево"),
    ("泉中水", "Вода источника", "Вода"), ("屋上土", "Земля на крыше", "Земля"),
    ("霹雳火", "Огонь молнии", "Огонь"), ("松柏木", "Дерево сосны", "Дерево"),
    ("长流水", "Вода длинного потока", "Вода"), ("砂石金", "Металл в песке", "Металл"),
    ("山下火", "Огонь у подножия", "Огонь"), ("平地木", "Дерево равнины", "Дерево"),
    ("壁上土", "Земля на стене", "Земля"), ("金箔金", "Сусальное золото", "Металл"),
    ("覆灯火", "Огонь лампы", "Огонь"), ("天河水", "Небесная вода", "Вода"),
    ("大驿土", "Земля тракта", "Земля"), ("钗钏金", "Металл украшений", "Металл"),
    ("桑柘木", "Дерево шелковицы", "Дерево"), ("大溪水", "Вода большого ручья", "Вода"),
    ("沙中土", "Земля в песке", "Земля"), ("天上火", "Небесный огонь", "Огонь"),
    ("石榴木", "Дерево граната", "Дерево"), ("大海水", "Вода моря", "Вода"),
]

EL_ORDER = ["Дерево", "Огонь", "Земля", "Металл", "Вода"]
STEL_IDX = [0, 0, 1, 1, 2, 2, 3, 3, 4, 4]   # стихия ствола как индекс
BEL_IDX = [4, 2, 0, 0, 2, 1, 1, 2, 3, 3, 2, 4]  # стихия ветви как индекс

# 0-based индекс шестидесятерицы по (ствол, ветвь)
_SEXAG = {}
for _i in range(60):
    _SEXAG[(_i % 10, _i % 12)] = _i


def gz_index(s: int, b: int) -> int:
    return _SEXAG[(s, b)]

# ---------------------------------------------------------------- солнце ----

def _lam_cum(n_days: float) -> float:
    """Непрерывная солнечная долгота (Meeus, низкая точность, ~0.01°)."""
    L = 280.460 + 0.9856474 * n_days
    g = math.radians(357.528 + 0.9856003 * n_days)
    return L + 1.915 * math.sin(g) + 0.020 * math.sin(2 * g)


def days_since(dt_utc: datetime) -> float:
    return (dt_utc - J2000).total_seconds() / 86400.0


def solar_lon(dt_utc: datetime) -> float:
    return _lam_cum(days_since(dt_utc)) % 360.0


def find_term(target_deg: float, after_utc: datetime) -> datetime:
    """Момент UTC, когда долгота Солнца впервые достигает target_deg."""
    n0 = days_since(after_utc)
    cum0 = _lam_cum(n0)
    m = math.ceil((cum0 - target_deg) / 360.0 - 1e-12)
    tc = target_deg + 360.0 * m
    delta = tc - cum0
    lo = n0 + delta / 1.03 - 3.0
    hi = n0 + delta / 0.94 + 3.0
    if lo < n0 - 1.0:
        lo = n0 - 1.0
    for _ in range(60):
        mid = (lo + hi) / 2.0
        if _lam_cum(mid) < tc:
            lo = mid
        else:
            hi = mid
    return J2000 + timedelta(days=(lo + hi) / 2.0)


def lichun_utc(year: int) -> datetime:
    """立春 данного календарного года."""
    return find_term(315.0, datetime(year, 1, 1, tzinfo=UTC))


def next_jie_utc(after_utc: datetime, direction: int) -> datetime:
    """Ближайшая 节 (долгота ≡ 15° mod 30°) вперёд (+1) или назад (−1)."""
    lam = solar_lon(after_utc)
    k = math.ceil((lam - 15.0) / 30.0)
    if direction > 0:
        target = (15 + 30 * k) % 360
        return find_term(target, after_utc)
    target = (15 + 30 * (k - 1)) % 360
    # окно 364 дня: прошлогоднее пересечение той же долготы всегда раньше окна
    return find_term(target, after_utc - timedelta(days=364))


# ------------------------------------------------------------------- бацзы --

def parse_date(s: str) -> date:
    y, m, d = (int(x) for x in s.strip().split("-"))
    return date(y, m, d)


def parse_time(s: str | None) -> tuple[int, int]:
    if not s:
        return 12, 0
    hh, mm = (int(x) for x in s.strip().split(":"))
    return hh, mm


def adjusted_year(d: date, tz: float, hh: int = 12, mm: int = 0) -> int:
    """Календарный год с учётом 立春."""
    birth_utc = datetime(d.year, d.month, d.day, hh, mm,
                         tzinfo=timezone(timedelta(hours=tz))).astimezone(UTC)
    return d.year if birth_utc >= lichun_utc(d.year) else d.year - 1


def ganzhi(gz_index: int) -> tuple[int, int]:
    """0-based индекс шестидесятерицы → (ствол, ветвь)."""
    return gz_index % 10, gz_index % 12


def pillars_data(d: date, hh: int, mm: int, tz: float, yeci: bool,
                 gender_male: bool = True) -> dict:
    birth_utc = datetime(d.year, d.month, d.day, hh, mm,
                         tzinfo=timezone(timedelta(hours=tz))).astimezone(UTC)

    # --- год ---
    yc_year = d.year if birth_utc >= lichun_utc(d.year) else d.year - 1
    ys, yb = ganzhi((yc_year - 4) % 60)

    # --- месяц (по долготе Солнца, 12 节) ---
    lam = solar_lon(birth_utc)
    mi = int(((lam - 315.0) % 360.0) // 30.0)      # 0 = 寅月
    ms = (ys * 2 + 2 + mi) % 10                    # 年上起月 (五虎遁)
    mb = (2 + mi) % 12

    # --- день (столп дня: (JDN + 49) % 60) ---
    day_ord = d.toordinal()
    zi_shift = bool(hh >= 23 and not yeci)
    if zi_shift:
        day_ord += 1
    d_gz = (day_ord + JDN_OFFSET + 49) % 60
    ds, db = ganzhi(d_gz)

    # --- час ---
    hb = ((hh + 1) // 2) % 12
    hs = (ds * 2 + hb) % 10                        # 日上起时 (五鼠遁)

    pillars = [
        ("год", ys, yb, yc_year), ("месяц", ms, mb, None),
        ("день", ds, db, None), ("час", hs, hb, None),
    ]
    el_count = {el: 0 for el in EL_ORDER}
    for _, s, b, _ in pillars:
        el_count[GAN_EL[s]] += 1
        el_count[BR_EL[b]] += 1

    out = {
        "date": d.isoformat(), "time": "%02d:%02d" % (hh, mm),
        "tz": tz, "yeci": yeci, "utc": birth_utc.isoformat(),
        "lichun_year": yc_year,
        "solar_lon": round(lam, 3),
        "pillars": [], "elements": el_count,
    }
    for name, s, b, yr in pillars:
        out["pillars"].append({
            "name": name, "hanzi": GAN[s] + ZHI[b],
            "stem": GAN[s], "stem_ru": GAN_RU[s], "stem_el": GAN_EL[s],
            "branch": ZHI[b], "branch_ru": ZHI_RU[b],
            "animal": ZH_RU[b], "branch_el": BR_EL[b],
            "hidden": "".join(GAN[i] for i in HIDDEN[b]),
            "nayin": NAYIN[gz_index(s, b) // 2][1] if name in ("год", "месяц", "день", "час") else "",
        })
    # 十神 трёх стволов относительно дневного
    out["shishen"] = {name: shishen(ds, s) for name, s, _, _ in pillars
                      if name != "день"}
    # --- 大运 (направление зависит от пола) ---
    yang_year = ys % 2 == 0
    forward = (yang_year and gender_male) or (not yang_year and not gender_male)
    out["dayun"] = dayun_calc(birth_utc, yang_year, forward, (ms, mb))
    return out


def shishen(ds: int, ts: int) -> str:
    """十神: дневной ствол ds → целевой ствол ts."""
    e_ds, e_ts = STEL_IDX[ds], STEL_IDX[ts]
    same = ds % 2 == ts % 2
    if e_ds == e_ts:
        return "比肩" if same else "劫财"
    if (e_ds + 1) % 5 == e_ts:
        return "食神" if same else "伤官"
    if (e_ts + 1) % 5 == e_ds:
        return "偏印" if same else "正印"
    if (e_ds + 2) % 5 == e_ts:
        return "偏财" if same else "正财"
    return "七杀" if same else "正官"


SHISHEN_RU = {
    "比肩": "ровня (равенство)", "劫财": "грабитель богатства (соперничество)",
    "食神": "бог пищи (творчество)", "伤官": "ранящий чиновник (талант+непокорность)",
    "偏财": "стороннее богатство", "正财": "прямое богатство",
    "偏印": "сторонняя печать", "正印": "прямая печать (поддержка)",
    "七杀": "семь убийств (давление)", "正官": "прямой чиновник (дисциплина)",
}


def dayun_calc(birth_utc, yang_year, forward, month_pillar):
    """Старт 大运: дни до ближайшей 节 ÷ 3."""
    if forward:
        t = next_jie_utc(birth_utc, +1)
        days = (t - birth_utc).total_seconds() / 86400.0
    else:
        t = next_jie_utc(birth_utc, -1)
        days = (birth_utc - t).total_seconds() / 86400.0
    whole = int(days // 3)
    months_extra = int(round((days - whole * 3) * 4))
    if months_extra >= 12:
        whole += 1
        months_extra = 0
    ms, mb = month_pillar
    seq = []
    for i in range(1, 4):
        if forward:
            seq.append(GAN[(ms + i) % 10] + ZHI[(mb + i) % 12])
        else:
            seq.append(GAN[(ms - i) % 10] + ZHI[(mb - i) % 12])
    return {
        "forward": forward, "days_to_jie": round(days, 2),
        "start_age_years": whole, "start_age_months": months_extra,
        "first_pillars": seq,
    }


# -------------------------------------------------------------------- 八宅 --

NUM_GUA = {1: "坎", 2: "坤", 3: "震", 4: "巽", 6: "乾", 7: "兑", 8: "艮", 9: "离"}
GUA_RU = {"乾": ("Цянь", "СЗ"), "坎": ("Кань", "С"), "艮": ("Гэнь", "СВ"),
          "震": ("Чжэнь", "В"), "巽": ("Сюнь", "ЮВ"), "离": ("Ли", "Ю"),
          "坤": ("Кунь", "ЮЗ"), "兑": ("Дуй", "З")}
BAZHAI_ORDER = ["乾", "坎", "艮", "震", "巽", "离", "坤", "兑"]
YOUNIAN_SONG = {"乾": "六天五祸绝延生", "坎": "五天生延绝祸六", "艮": "六绝祸生延天五",
                "震": "延生祸绝五天六", "巽": "天五六祸生绝延", "离": "六五绝延祸生天",
                "坤": "天延绝生祸五六", "兑": "生祸延绝六五天"}
YOUNIAN_NAME = {"生": "生气", "延": "延年", "天": "天医", "祸": "祸害",
                "六": "六煞", "五": "五鬼", "绝": "绝命"}
YOUNIAN_NOTE = {"生气": "Шэн-ци — процветание (верх. удача)",
                "延年": "Янь-нянь — долголетие (верх. удача)",
                "天医": "Тянь-и — здоровье (сред. удача)",
                "伏位": "Фу-вэй — стабильность (мал. удача)",
                "祸害": "Хо-хай — беды (мал. неудача)",
                "六煞": "Лю-ша — шестеро убийц (сред. неудача)",
                "五鬼": "У-гуй — пять духов (сильн. неудача)",
                "绝命": "Цзюэ-мин — обрыв жизни (сильн. неудача)"}
EAST_FOUR = {"坎", "离", "震", "巽"}


def gua_data(d: date, gender: str) -> dict:
    y = adjusted_year(d, 8.0)
    male = gender.lower().startswith("m") or gender.lower() in ("м", "муж")
    if male:
        raw = (11 - y % 9) % 9 or 9
    else:
        raw = (y % 9 + 4) % 9 or 9
    num = (2 if male else 8) if raw == 5 else raw
    gua = NUM_GUA[num]

    i = BAZHAI_ORDER.index(gua)
    others = [BAZHAI_ORDER[(i + k) % 8] for k in range(1, 8)]
    table = {"伏位": gua}
    for g2, ch in zip(others, YOUNIAN_SONG[gua]):
        table[YOUNIAN_NAME[ch]] = g2
    dirs = {name: {"gua": g2, "dir": GUA_RU[g2][1], "note": YOUNIAN_NOTE[name]}
            for name, g2 in table.items()}
    lucky = [n for n in ("生气", "延年", "天医", "伏位") if n in dirs]
    unlucky = [n for n in ("祸害", "六煞", "五鬼", "绝命") if n in dirs]
    return {
        "date": d.isoformat(), "lichun_year": y, "gender": "м" if male else "ж",
        "raw": raw, "number": num, "gua": gua, "gua_ru": GUA_RU[gua][0],
        "group": "Восточные (东四)" if gua in EAST_FOUR else "Западные (西四)",
        "jigong": ("муж. 5 → 坤(2)" if male else "жен. 5 → 艮(8)") if raw == 5 else "",
        "directions": dirs, "lucky": lucky, "unlucky": unlucky,
    }


# ------------------------------------------------------------- летящие звёзды

FLY = [6, 7, 8, 9, 1, 2, 3, 4]  # траектория Ло-шу от центра
MOUNTAINS = {  # имя → (двор, 元龙 0地/1天/2人, инь=False/ян=True)
    "壬": (1, 0, True), "子": (1, 1, False), "癸": (1, 2, False),
    "丑": (8, 0, False), "艮": (8, 1, True), "寅": (8, 2, True),
    "甲": (3, 0, True), "卯": (3, 1, False), "乙": (3, 2, False),
    "辰": (4, 0, False), "巽": (4, 1, True), "巳": (4, 2, True),
    "丙": (9, 0, True), "午": (9, 1, False), "丁": (9, 2, False),
    "未": (2, 0, False), "坤": (2, 1, True), "申": (2, 2, True),
    "庚": (7, 0, True), "酉": (7, 1, False), "辛": (7, 2, False),
    "戌": (6, 0, False), "乾": (6, 1, True), "亥": (6, 2, True),
}
DEG_ORDER = ["子", "癸", "丑", "艮", "寅", "甲", "卯", "乙", "辰", "巽", "巳",
             "丙", "午", "丁", "未", "坤", "申", "庚", "酉", "辛", "戌", "乾",
             "亥", "壬"]
PALACE_RU = {1: "С", 2: "ЮЗ", 3: "В", 4: "ЮВ", 5: "центр",
             6: "СЗ", 7: "З", 8: "СВ", 9: "Ю"}
BR_PALACE = {0: 1, 1: 8, 2: 8, 3: 3, 4: 4, 5: 4, 6: 9, 7: 2, 8: 2, 9: 7, 10: 6, 11: 6}
PALACE_OPP = {1: 9, 9: 1, 2: 8, 8: 2, 3: 7, 7: 3, 4: 6, 6: 4, 5: 5}


def flight(center: int, forward: bool) -> dict[int, int]:
    res = {5: center}
    for k, pal in enumerate(FLY, start=1):
        v = ((center - 1) + k) % 9 if forward else ((center - 1) - k) % 9
        res[pal] = v + 1
    return res


def mountain_from_deg(deg: float) -> str:
    return DEG_ORDER[int(round(deg / 15.0)) % 24]


def period_of(year: int) -> int:
    if year < 1864:
        raise ValueError("год до 1864: периоды 元运 неприменимы")
    p = (year - 1864) // 20 + 1
    return p if p <= 9 else 9


def feixing_data(facing_deg: float | None, facing_name: str | None,
                 year: int, annual: int | None, tz: float) -> dict:
    y = adjusted_year(date(year, 6, 1), tz)  # середина года — точно после 立春
    period = period_of(y)

    if facing_name:
        m_fac = facing_name
        idx = DEG_ORDER.index(facing_name)
    else:
        idx = int(round((facing_deg % 360) / 15.0)) % 24
        m_fac = DEG_ORDER[idx]
    m_sit = DEG_ORDER[(idx + 12) % 24]
    pal_sit, yuan_sit, yang_sit = MOUNTAINS[m_sit]
    pal_fac, yuan_fac, yang_fac = MOUNTAINS[m_fac]

    chart = flight(period, True)
    ms = chart[pal_sit]
    fs = chart[pal_fac]

    def polarity(star, yuan, own_yang, own_palace):
        if star == 5:
            return own_yang
        for name, (pal, yl, yng) in MOUNTAINS.items():
            if pal == star and yl == yuan:
                return yng
        return own_yang  # недостижимо

    mchart = flight(ms, polarity(ms, yuan_sit, yang_sit, pal_sit))
    fchart = flight(fs, polarity(fs, yuan_fac, yang_fac, pal_fac))

    full = {pal: (mchart[pal], chart[pal], fchart[pal]) for pal in range(1, 10)}
    if mchart[pal_sit] == period and fchart[pal_fac] == period:
        fmt = "旺山旺向 (旺山旺向 — лучший формат)"
    elif fchart[pal_fac] == period and mchart[pal_fac] == period:
        fmt = "双星到向 (двойная звезда на фасаде)"
    elif mchart[pal_sit] == period and fchart[pal_sit] == period:
        fmt = "双星到坐 (двойная звезда на сидячей)"
    elif mchart[pal_fac] == period and fchart[pal_sit] == period:
        fmt = "上山下水 (перекрёстный сложный формат)"
    else:
        fmt = "смешанный формат"

    out = {
        "lichun_year": y, "period": period, "facing": m_fac, "sitting": m_sit,
        "facing_deg": facing_deg, "grid": full, "format": fmt,
        "grid_ru": {PALACE_RU[p]: full[p] for p in full},
        "annual": None,
    }
    if annual:
        ay = adjusted_year(date(annual, 6, 1), tz)
        c = (10 - ay % 9) % 9 + 1
        ach = flight(c, True)
        pal5 = [p for p, v in ach.items() if v == 5][0]
        pal2 = [p for p, v in ach.items() if v == 2][0]
        br = (ay - 4) % 12
        # 申子辰 → Ю(巳午未); 寅午戌 → С(亥子丑); 巳酉丑 → В(寅卯辰); 亥卯未 → З(申酉戌)
        sansha = {0: "Ю (巳午未)", 4: "Ю (巳午未)", 8: "Ю (巳午未)",
                  2: "С (亥子丑)", 6: "С (亥子丑)", 10: "С (亥子丑)",
                  5: "В (寅卯辰)", 9: "В (寅卯辰)", 1: "В (寅卯辰)",
                  11: "З (申酉戌)", 3: "З (申酉戌)", 7: "З (申酉戌)"}[br]
        out["annual"] = {
            "year": ay, "hanzi": GAN[(ay - 4) % 10] + ZHI[br],
            "center": c, "annual_grid": ach,
            "wuhuang": PALACE_RU[pal5], "erhei": PALACE_RU[pal2],
            "taisui": PALACE_RU[BR_PALACE[br]],
            "suipo": PALACE_RU[PALACE_OPP[BR_PALACE[br]]],
            "sansha": sansha,
        }
    return out


# -------------------------------------------------------------- нумерология --

RU_VALUES = {"А": 1, "И": 1, "С": 1, "Ъ": 1, "Б": 2, "Й": 2, "Т": 2, "Ы": 2,
             "В": 3, "К": 3, "У": 3, "Ь": 3, "Г": 4, "Л": 4, "Ф": 4, "Э": 4,
             "Д": 5, "М": 5, "Х": 5, "Ю": 5, "Е": 6, "Н": 6, "Ц": 6, "Я": 6,
             "Ё": 7, "О": 7, "Ч": 7, "Ж": 8, "П": 8, "Ш": 8, "З": 9, "Р": 9,
             "Щ": 9}
VOWELS = set("АЕЁИОУЫЭЮЯ")

NUM_RU = {1: "лидерство, самостоятельность", 2: "партнёрство, чуткость",
          3: "творчество, общение", 4: "порядок, труд, система",
          5: "свобода, перемены", 6: "забота, семья, ответственность",
          7: "анализ, поиск смысла", 8: "управление, деньги, амбиции",
          9: "служение, широта, завершение циклов",
          11: "мастер-число: вдохновитель", 22: "мастер-число: строитель",
          33: "мастер-число: учитель"}

PSY_LABEL = {1: "Характер, воля", 2: "Энергия", 3: "Интерес/творчество",
             4: "Здоровье", 5: "Логика, интуиция", 6: "Труд, мастерство",
             7: "Удача", 8: "Долг, доброта", 9: "Память, ум"}


def reduce_num(n: int, keep_master: bool = True) -> int:
    while n > 9:
        if keep_master and n in (11, 22, 33):
            return n
        n = sum(int(c) for c in str(n))
    return n


def numerology_data(d: date, name: str | None, year_now: int) -> dict:
    d_r, m_r, y_r = (reduce_num(d.day, False), reduce_num(d.month, False),
                     reduce_num(d.year, False))
    life = reduce_num(d_r + m_r + y_r)
    out = {
        "date": d.isoformat(),
        "life_path": life, "life_path_meaning": NUM_RU.get(life, ""),
        "birthday_number": reduce_num(d.day, False),
    }
    if name:
        letters = [RU_VALUES[ch] for ch in name.upper() if ch in RU_VALUES]
        expr = reduce_num(sum(letters))
        vowels = sum(RU_VALUES[ch] for ch in name.upper()
                     if ch in RU_VALUES and ch in VOWELS)
        cons = sum(RU_VALUES[ch] for ch in name.upper()
                   if ch in RU_VALUES and ch not in VOWELS
                   and ch not in ("Ъ", "Ь"))
        out["name"] = name
        out["expression"] = expr
        out["expression_meaning"] = NUM_RU.get(expr, "")
        out["soul"] = reduce_num(vowels)
        out["personality"] = reduce_num(cons)
        out["maturity"] = reduce_num(life + expr)
    py = reduce_num(d_r + m_r + reduce_num(year_now, False), False)
    out["personal_year"] = py
    out["personal_year_meaning"] = {
        1: "старт новых циклов", 2: "партнёрства и терпение",
        3: "творчество и общение", 4: "труд и фундамент",
        5: "перемены и свобода", 6: "семья и обязанности",
        7: "обучение и уединение", 8: "деньги и статус",
        9: "завершение циклов"}[py]
    # --- психоматрица ---
    digits = [int(c) for c in "%02d%02d%04d" % (d.day, d.month, d.year)]
    n1 = sum(digits)
    n2 = sum(int(c) for c in str(n1))
    n3 = n1 - 2 * int(str(d.day)[0])
    n4 = sum(int(c) for c in str(n3))
    all_digits = digits + [int(c) for c in str(n1)] + [int(c) for c in str(n2)] \
        + [int(c) for c in str(n3)] + [int(c) for c in str(n4)]
    counts = {k: all_digits.count(k) for k in range(1, 10)}
    out["psychomatrix"] = {
        "working_numbers": [n1, n2, n3, n4], "cells": counts,
        "labels": PSY_LABEL,
    }
    return out


# ------------------------------------------------------------- совместимость --

ZH6 = {0: 1, 2: 11, 3: 10, 4: 9, 5: 8, 6: 7}  # 子丑 寅亥 卯戌 辰酉 巳申 午未
SANHE = [{8, 0, 4}, {2, 6, 10}, {5, 9, 1}, {11, 3, 7}]
SANHUI = [{11, 0, 1}, {2, 3, 4}, {5, 6, 7}, {8, 9, 10}]
HAI = {0: 7, 1: 6, 2: 5, 3: 4, 8: 11, 9: 10}
PO = {0: 9, 3: 6, 1: 4, 5: 8, 2: 11, 7: 10}
GAN_HE = {0: 5, 1: 6, 2: 7, 3: 8, 4: 9}
GAN_CHONG = [(0, 6), (1, 7), (2, 8), (3, 9)]
XING_GROUPS = [{2, 5, 8}, {1, 10, 7}]
SELF_XING = {4, 6, 9, 11}

BANDS = [(90, "天作之合 «Союз, созданный небом»"),
         (75, "佳偶天成 «Прекрасная пара»"),
         (60, "尚可配对 «Достойное сочетание»"),
         (45, "需要用心 «Требует усилий»"),
         (30, "有缘无分 «Мелкая карма»"),
         (0, "不建议强求 «Не стоит настаивать»")]

SHISHEN_SCORE = {"正官": 90, "正财": 90, "正印": 85, "食神": 85, "比肩": 70,
                 "偏财": 75, "偏印": 65, "劫财": 55, "伤官": 50, "七杀": 45}


def branch_relation(a: int, b: int) -> list[str]:
    rel = []
    if ZH6.get(a) == b or ZH6.get(b) == a:
        rel.append("六合")
    if a != b and any(a in g and b in g for g in SANHE):
        rel.append("三合")
    if a != b and any(a in g and b in g for g in SANHUI):
        rel.append("三会")
    if (a + 6) % 12 == b:
        rel.append("六冲")
    if HAI.get(a) == b or HAI.get(b) == a:
        rel.append("六害")
    for g in XING_GROUPS:
        if a in g and b in g and a != b:
            rel.append("三刑")
            break
    if a == b and a in SELF_XING:
        rel.append("自刑")
    if PO.get(a) == b or PO.get(b) == a:
        rel.append("六破")
    return rel


def stem_relation(a: int, b: int) -> list[str]:
    rel = []
    if GAN_HE.get(a) == b or GAN_HE.get(b) == a:
        rel.append("天干五合")
    if (a, b) in GAN_CHONG or (b, a) in GAN_CHONG:
        rel.append("天干冲")
    return rel


def nayin_of(year_gz: int) -> tuple[str, str]:
    return NAYIN[year_gz // 2][1], NAYIN[year_gz // 2][2]


def match_data(c1: dict, c2: dict) -> dict:
    p1 = {p["name"]: p for p in c1["pillars"]}
    p2 = {p["name"]: p for p in c2["pillars"]}
    y1, y2 = (p1["год"], p2["год"])
    d1, d2 = (p1["день"], p2["день"])
    gi = lambda p: gz_index(GAN.index(p["stem"]), ZHI.index(p["branch"]))
    y1_gz, y2_gz = gi(y1), gi(y2)

    # 1. стволы (15%)
    stem_rel = stem_relation(GAN.index(y1["stem"]), GAN.index(y2["stem"])) + \
        stem_relation(GAN.index(d1["stem"]), GAN.index(d2["stem"]))
    s = 50
    for r in stem_rel:
        s += 30 if r == "天干五合" else -25
    dims = {"stems": max(0, min(100, s)), "stems_rel": stem_rel}

    # 2. союзы ветвей (20%)
    rels_y = branch_relation(ZHI.index(y1["branch"]), ZHI.index(y2["branch"]))
    rels_d = branch_relation(ZHI.index(d1["branch"]), ZHI.index(d2["branch"]))
    s = 40
    for rels in (rels_y, rels_d):
        if "三合" in rels:
            s += 35
        if "六合" in rels:
            s += 30
        if "三会" in rels:
            s += 20
        if not rels:
            s += 10
    dims["unions"] = max(0, min(100, s))

    # 3. столкновения ветвей (15%, штрафной)
    s = 100
    for rels in (rels_y, rels_d):
        s -= 55 * rels.count("六冲") + 35 * rels.count("三刑") + \
            40 * rels.count("六害") + 25 * rels.count("六破") + \
            10 * rels.count("自刑")
    dims["clashes"] = max(0, s)

    # 4. дневные столпы (25%)
    ss = SHISHEN_SCORE.get(shishen(GAN.index(d1["stem"]), GAN.index(d2["stem"])), 60)
    bs = 60
    if "三合" in rels_d or "六合" in rels_d:
        bs = 100
    elif "三会" in rels_d:
        bs = 85
    elif "六冲" in rels_d:
        bs = 15
    elif "六害" in rels_d:
        bs = 25
    elif "三刑" in rels_d:
        bs = 30
    elif "六破" in rels_d:
        bs = 40
    dims["day_pillar"] = 0.5 * ss + 0.5 * bs
    shishen_ab = shishen(GAN.index(d1["stem"]), GAN.index(d2["stem"]))
    shishen_ba = shishen(GAN.index(d2["stem"]), GAN.index(d1["stem"]))

    # 5. взаимодополнение стихий (15%)
    e1, e2 = c1["elements"], c2["elements"]
    miss1 = [e for e in EL_ORDER if e1[e] == 0]
    miss2 = [e for e in EL_ORDER if e2[e] == 0]

    def cover(miss, other):
        if not miss:
            return 90
        return 100.0 * sum(1 for e in miss if other[e] > 0) / len(miss)
    dims["elements"] = (cover(miss1, e2) + cover(miss2, e1)) / 2.0

    # 6. найнь (10%)
    n1_ru, n1_el = nayin_of(y1_gz)
    n2_ru, n2_el = nayin_of(y2_gz)
    i1, i2 = EL_ORDER.index(n1_el), EL_ORDER.index(n2_el)
    if n1_ru == n2_ru:
        s = 90
    elif (i1 + 1) % 5 == i2 or (i2 + 1) % 5 == i1:
        s = 85
    elif (i1 + 2) % 5 == i2 or (i2 + 2) % 5 == i1:
        s = 45
    else:
        s = 60
    dims["nayin"] = s

    total = (0.15 * dims["stems"] + 0.20 * dims["unions"] +
             0.15 * dims["clashes"] + 0.25 * dims["day_pillar"] +
             0.15 * dims["elements"] + 0.10 * dims["nayin"])
    total = round(total, 1)
    band = next(label for th, label in BANDS if total >= th)
    zod_rel = rels_y

    return {
        "score": total, "band": band,
        "dims": {k: (round(v, 1) if isinstance(v, float) else v)
                 for k, v in dims.items() if not k.endswith("_rel")},
        "zodiac": zod_rel, "year_stems": stem_rel,
        "shishen": {"1→2": shishen_ab, "2→1": shishen_ba,
                    "значение": SHISHEN_RU[shishen_ab]},
        "nayin": {"1": n1_ru, "2": n2_ru},
        "missing_elements": {"1": miss1, "2": miss2},
        "day_branches_rel": rels_d,
        "guа_note": "дополнительно можно сравнить группы гуа (команда gua): "
                    "восточный+восточный или западный+западный — гармония",
    }


def zodiac_verdict(a: int, b: int) -> dict:
    rels = branch_relation(a, b)
    if "六合" in rels:
        return {"rel": "六合", "score": 95, "stars": "⭐⭐⭐⭐⭐",
                "verdict": "лучший тип пары: скрытая гармония, взаимное притяжение"}
    if "三合" in rels:
        return {"rel": "三合", "score": 85, "stars": "⭐⭐⭐⭐",
                "verdict": "глубокое взаимопонимание, общие интересы и ритм"}
    if "三会" in rels:
        return {"rel": "三会", "score": 80, "stars": "⭐⭐⭐⭐",
                "verdict": "сезонный союз: близкие темпераменты из одного «сезона»"}
    if "六冲" in rels:
        return {"rel": "六冲", "score": 50, "stars": "⭐⭐",
                "verdict": "контраст темпераментов: искры и конфликты; важно "
                           "уважать различия (冲 — не приговор!)"}
    if "六害" in rels:
        return {"rel": "六害", "score": 60, "stars": "⭐⭐⭐",
                "verdict": "недопонимание накапливается незаметно: проговаривайте мелочи"}
    if "三刑" in rels or "自刑" in rels:
        return {"rel": "刑", "score": 55, "stars": "⭐⭐⭐",
                "verdict": "периодические трения и упрямство: учиться уступать"}
    if "六破" in rels:
        return {"rel": "破", "score": 65, "stars": "⭐⭐⭐",
                "verdict": "мелкие помехи в быту, в целом нейтрально"}
    return {"rel": "普通", "score": 70, "stars": "⭐⭐⭐",
            "verdict": "нейтральное сочетание — всё зависит от усилий обоих"}


# ------------------------------------------------------------------ вывод ----

def fmt_pillars(c: dict) -> str:
    lines = ["Четыре столпа (八字):"]
    lines.append("  %-6s %-5s %-14s %-10s %s" %
                 ("столб", "字", "транскр.", "стихия", "прим."))
    for p in c["pillars"]:
        ss = c["shishen"].get(p["name"], "—日主")
        lines.append("  %-6s %-5s %-14s %-10s %s%s" % (
            p["name"], p["hanzi"],
            "%s-%s" % (p["stem_ru"], p["branch_ru"]),
            "%s / %s(%s)" % (p["stem_el"], p["animal"], p["branch_el"]),
            ("скрытые: " + p["hidden"] + " ") if p["hidden"] else "",
            ("十神: %s (%s)" % (ss, SHISHEN_RU[ss])) if ss in SHISHEN_RU else
            ("дневной господин" if p["name"] == "день" else "")))
    els = " ".join("%s:%d" % (e, n) for e, n in c["elements"].items())
    lines.append("Пять стихий (видимые 8 знаков): " + els)
    lines.append("Найнь (纳音): " + "; ".join(
        "%s — %s" % (p["name"], p["nayin"]) for p in c["pillars"]))
    du = c["dayun"]
    lines.append("大运: %s порядок, старт ~%d лет %d мес. (до 节 %.1f дн.); "
                 "первые такты: %s" % (
                     "прямой" if du["forward"] else "обратный",
                     du["start_age_years"], du["start_age_months"],
                     du["days_to_jie"], " ".join(du["first_pillars"])))
    return "\n".join(lines)


def cmd_pillars(a):
    d = parse_date(a.date)
    hh, mm = parse_time(a.time)
    male = a.gender.lower().startswith(("m", "м"))
    c = pillars_data(d, hh, mm, a.tz, a.yeci, male)
    if a.json:
        print(json.dumps(c, ensure_ascii=False, indent=2))
        return
    print(fmt_pillars(c))


def cmd_gua(a):
    g = gua_data(parse_date(a.date), a.gender)
    if a.json:
        print(json.dumps(g, ensure_ascii=False, indent=2))
        return
    print("Число гуа (命卦): %d %s (%s), группа: %s%s" % (
        g["number"], g["gua"], g["gua_ru"], g["group"],
        ("; " + g["jigong"]) if g["jigong"] else ""))
    print("Восемь направлений (游年):")
    for name in g["lucky"] + g["unlucky"]:
        dd = g["directions"][name]
        print("  %-4s → %-2s (%s): %s" % (name, dd["dir"], dd["gua"], dd["note"]))


def cmd_feixing(a):
    d = feixing_data(a.facing, a.facing_name, a.year, a.annual, a.tz)
    if a.json:
        print(json.dumps(d, ensure_ascii=False, indent=2))
        return
    print("Период (元运): %d (год заселения %d, календарь 立春)" % (
        d["period"], d["lichun_year"]))
    print("Сидячая гора: %s; фасад: %s%s" % (
        d["sitting"], d["facing"],
        " (замер %.0f°)" % d["facing_deg"] if d["facing_deg"] is not None else ""))
    print("Формат: " + d["format"])
    print("Карта 下卦 [горная / периода / направления], юг сверху:")
    for row in ([4, 9, 2], [3, 5, 7], [8, 1, 6]):
        cells = []
        for pal in row:
            m, p, f = d["grid"][pal]
            cells.append("%d %d %d" % (m, p, f))
        print("  | " + "  |  ".join(cells) + " |")
    print("  (" + ", ".join("%s" % PALACE_RU[pal] for pal in (4, 9, 2, 3, 5, 7, 8, 1, 6)) + ")")
    if d["annual"]:
        an = d["annual"]
        print("Годовые звёзды %s (%d): центр %d; 五黄 — %s, 二黑 — %s; "
              "太岁 — %s, 岁破 — %s, 三煞 — %s" % (
                  an["hanzi"], an["year"], an["center"], an["wuhuang"],
                  an["erhei"], an["taisui"], an["suipo"], an["sansha"]))
    edge = (d["facing_deg"] is not None and
            abs((d["facing_deg"] % 15.0) - 7.5) < 0.05)
    if edge or d["facing_deg"] is None:
        print("Примечание: " + ("замер точно на границе горы (±7.5°) — проверьте "
                                "направление" if edge else
                                "фасад задан горой, а не градусами: точность ниже; "
                                "при отклонении >3° обычно нужен 替卦, "
                                "скрипт его не считает"))


def cmd_numerology(a):
    nd = numerology_data(parse_date(a.date), a.name, a.year_now)
    if a.json:
        print(json.dumps(nd, ensure_ascii=False, indent=2))
        return
    print("Нумерология (%s):" % nd["date"])
    print("  Число жизненного пути: %d — %s" % (
        nd["life_path"], nd["life_path_meaning"]))
    print("  Число дня рождения: %d" % nd["birthday_number"])
    if "expression" in nd:
        print("  Число выражения: %d — %s" % (
            nd["expression"], nd["expression_meaning"]))
        print("  Число души: %d; число личности: %d; число зрелости: %d" % (
            nd["soul"], nd["personality"], nd["maturity"]))
    print("  Личный год (%d): %d — %s" % (
        a.year_now, nd["personal_year"], nd["personal_year_meaning"]))
    pm = nd["psychomatrix"]
    print("  Психоматрица (рабочие числа: %s):" % ", ".join(map(str, pm["working_numbers"])))
    grid = [(1, 2, 3), (4, 5, 6), (7, 8, 9)]
    for row in grid:
        print("    " + "  ".join("%d:%d %s" % (k, pm["cells"][k], pm["labels"][k][:14])
                                 for k in row))


def cmd_match(a):
    male1 = a.g1.lower().startswith(("m", "м"))
    male2 = a.g2.lower().startswith(("m", "м"))
    c1 = pillars_data(parse_date(a.d1), *parse_time(a.t1), a.tz, False, male1)
    c2 = pillars_data(parse_date(a.d2), *parse_time(a.t2), a.tz, False, male2)
    res = match_data(c1, c2)
    if a.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return
    p1, p2 = c1["pillars"], c2["pillars"]
    print("八字合婚 (совместимость по бацзы, веса yinyuan-skills):")
    print("  Партнёр 1: %s %s (%s)" % (
        p1[0]["hanzi"], p1[2]["hanzi"], ZH_RU[ZHI.index(p1[0]["branch"])]))
    print("  Партнёр 2: %s %s (%s)" % (
        p2[0]["hanzi"], p2[2]["hanzi"], ZH_RU[ZHI.index(p2[0]["branch"])]))
    names = {"stems": "стволы (15%)", "unions": "союзы ветвей (20%)",
             "clashes": "столкновения (15%)", "day_pillar": "дневные столпы (25%)",
             "elements": "взаимодополнение 五行 (15%)", "nayin": "найнь (10%)"}
    print("  Измерения:")
    for k, lbl in names.items():
        print("    %-24s %s" % (lbl, res["dims"][k]))
    print("  Зодиак (годовые ветви): %s" % (res["zodiac"] or "普通"))
    print("  Отношения стволов: %s" % (res["year_stems"] or "нет"))
    print("  十神: 1→2 %s; 2→1 %s (%s)" % (
        res["shishen"]["1→2"], res["shishen"]["2→1"],
        res["shishen"]["значение"]))
    print("  Найнь: %s + %s" % (res["nayin"]["1"], res["nayin"]["2"]))
    print("  Недостающие стихии: 1 — %s; 2 — %s" % (
        ", ".join(res["missing_elements"]["1"]) or "нет",
        ", ".join(res["missing_elements"]["2"]) or "нет"))
    print("ИТОГ: %s — %s" % (res["score"], res["band"]))
    print(res["guа_note"])


def cmd_zodiac(a):
    d1, d2 = parse_date(a.d1), parse_date(a.d2)
    y1 = adjusted_year(d1, a.tz)
    y2 = adjusted_year(d2, a.tz)
    b1, b2 = (y1 - 4) % 12, (y2 - 4) % 12
    v = zodiac_verdict(b1, b2)
    if a.json:
        print(json.dumps(dict(v, b1=b1, b2=b2), ensure_ascii=False, indent=2))
        return
    print("Зодиакальная совместимость (生肖):")
    print("  %s (%s) + %s (%s)" % (ZH_RU[b1], ZHI[b1], ZH_RU[b2], ZHI[b2]))
    print("  Отношение: %s | %s" % (v["rel"], v["stars"]))
    print("  Ориентир: %s/100" % v["score"])
    print("  " + v["verdict"])


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("pillars")
    p.add_argument("--date", required=True, help="YYYY-MM-DD")
    p.add_argument("--time", default="12:00", help="HH:MM (местное)")
    p.add_argument("--tz", type=float, default=8.0, help="сдвиг от UTC, часов")
    p.add_argument("--gender", default="m", help="m/м или f/ж (для 大运)")
    p.add_argument("--yeci", action="store_true",
                   help="поздний цзы: 23:00–24:00 = текущий день")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_pillars)

    p = sub.add_parser("gua")
    p.add_argument("--date", required=True)
    p.add_argument("--gender", required=True, help="m/ж или f/ж")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_gua)

    p = sub.add_parser("feixing")
    p.add_argument("--facing", type=float, default=None, help="фасад в градусах")
    p.add_argument("--facing-name", dest="facing_name", default=None,
                   help="гора фасада: 子/癸/丑/艮/寅/甲/卯/乙/辰/巽/巳/丙/午/丁/未/坤/申/庚/酉/辛/戌/乾/亥/壬")
    p.add_argument("--year", type=int, required=True, help="год заселения")
    p.add_argument("--annual", type=int, default=None, help="год для годовых звёзд")
    p.add_argument("--tz", type=float, default=8.0)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_feixing)

    p = sub.add_parser("numerology")
    p.add_argument("--date", required=True)
    p.add_argument("--name", default=None, help="полное имя (кириллица)")
    p.add_argument("--year-now", type=int, default=datetime.now().year)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_numerology)

    p = sub.add_parser("match")
    p.add_argument("--d1", required=True); p.add_argument("--t1", default="12:00")
    p.add_argument("--g1", required=True); p.add_argument("--d2", required=True)
    p.add_argument("--t2", default="12:00"); p.add_argument("--g2", required=True)
    p.add_argument("--tz", type=float, default=8.0)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_match)

    p = sub.add_parser("zodiac")
    p.add_argument("--d1", required=True); p.add_argument("--d2", required=True)
    p.add_argument("--tz", type=float, default=8.0)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_zodiac)

    args = ap.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
