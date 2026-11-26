"""landform: чтение пакета vector-geo-site и сведение 龍穴砂水向 с картой звёзд.

Вставляется в scripts/fengshui_bazi_calc.py (только стандартная библиотека).
Правило: пакет измеряет, навык читает. Поля с уверенностью low не дают категоричных выводов.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

MOUNTAIN_CENTER = {  # 24 горы: центр сектора в градусах
    "子": 0, "癸": 15, "丑": 30, "艮": 45, "寅": 60, "甲": 75, "卯": 90, "乙": 105,
    "辰": 120, "巽": 135, "巳": 150, "丙": 165, "午": 180, "丁": 195, "未": 210,
    "坤": 225, "申": 240, "庚": 255, "酉": 270, "辛": 285, "戌": 300, "乾": 315,
    "亥": 330, "壬": 345,
}

MOUNTAIN_RU = {
    "子": "север", "癸": "север-северо-восток", "丑": "северо-восток", "艮": "северо-восток",
    "寅": "восток-северо-восток", "甲": "восток", "卯": "восток", "乙": "восток-юго-восток",
    "辰": "юго-восток", "巽": "юго-восток", "巳": "юго-восток", "丙": "юг",
    "午": "юг", "丁": "юг-юго-запад", "未": "юго-запад", "坤": "юго-запад",
    "申": "запад-юго-запад", "庚": "запад", "酉": "запад", "辛": "запад-северо-запад",
    "戌": "северо-запад", "乾": "северо-запад", "亥": "северо-запад", "壬": "север",
}

# R8: минимальные версии, с которыми навык умеет читать пакет
SUPPORTED_SCHEMAS = {"site_pack/1", "site_pack/2"}
MIN_SCHEMA = "site_pack/1"
MIN_ALGO = {"water": (6, 1, 0), "terrain": (2, 0, 0), "pack": (1, 2, 0),
            "climate": (1, 0, 0)}
CURRENT_PERIOD = (9, 2024, 2043)

SPIRIT_RU = {"tortoise": "черепаха (спина)", "bird": "птица (фасад)",
             "dragon": "дракон (слева)", "tiger": "тигр (справа)"}


def _get(obj, *path, default=None):
    cur = obj
    for key in path:
        if not isinstance(cur, dict) or key not in cur:
            return default
        cur = cur[key]
    return cur


def _num(value):
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


AQUATIC_KINDS = {"river", "stream", "canal", "culvert"}

# Водоём меньше этого в отчёт не идёт: у контура такого размера нет ни стороны, ни влияния,
# он остаётся только в water.geojson (E-020 доп., порог описан в docs/calc/rivers.md).
AREA_MIN_M2 = 500.0

# E-021: положение участка относительно петли — словами, а не кодом поля
LOOP_POSITION_RU = {
    "inside": "участок охвачен водой (玉帶)",
    "outside_convex": "反弓: вода выгибается от участка",
    "outside_concave": "участок с внешней стороны вогнутости петли",
}


def _is_area(item: dict) -> bool:
    """Контур водоёма (E-018 в vector-geo-site): речных полей у него нет."""
    return item.get("geom", "line") == "area"


def _hidden_share(item: dict) -> float:
    value = _num(item.get("hidden_share"))
    return value if value is not None else 0.0


def _same_mountains_in_text(text: str) -> bool:
    """Вход и выход в одной горе — по строке отчёта (сторожевой тест E-020 п.2)."""
    found = re.search(r"вход (.+?), выход (.+?),", text)
    return bool(found and found.group(1) == found.group(2))


SPIRIT_ALIASES = {"tortoise": ("tortoise", "back"), "bird": ("bird", "front"),
                  "dragon": ("dragon", "left"), "tiger": ("tiger", "right")}


def _normalize_spirits(spirits: dict) -> dict:
    """Хранители сторон: схема 1 зовёт их именами духов, схема 2 (pack 2.0.0) — back/front/left/right.

    До PR 11 навык читает оба набора и приводит к одному виду: пакет 2.0.0 не должен
    «не открываться» только из-за переименования.
    """
    if not spirits:
        return spirits or {}
    out: dict = {}
    for canonical, aliases in SPIRIT_ALIASES.items():
        for alias in aliases:
            if alias in spirits:
                out[canonical] = spirits[alias]
                break
    diff = spirits.get("dragon_vs_tiger", spirits.get("left_vs_right"))
    if diff is not None:
        out["dragon_vs_tiger"] = diff
    return out


def _mountain_ru(name: str | None) -> str:
    if not name:
        return "—"
    return "%s (%s)" % (name, MOUNTAIN_RU.get(name, "?")) if name in MOUNTAIN_CENTER else str(name)


def _version_tuple(text) -> tuple[int, ...]:
    parts = []
    for chunk in str(text or "0").split("."):
        digits = "".join(ch for ch in chunk if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts) or (0,)


def check_pack_versions(pack: dict) -> list[str]:
    """R8: схема обязана совпадать, старые версии расчёта дают предупреждение.

    Схема другая — читать нельзя (структура могла измениться). Версия воды/рельефа/пакета
    старее минимальной — читаем, но предупреждаем: числа могли считаться по старым правилам.
    """
    schema = pack.get("schema")
    if schema not in SUPPORTED_SCHEMAS:
        raise ValueError("пакет собран по схеме %r, навык читает %r: пересоберите пакет "
                         "в vector-geo-site" % (schema, ", ".join(sorted(SUPPORTED_SCHEMAS))))
    # site_pack/2 = pack 2.0.0: стороны названы back/front/left/right (H4). Пока навык не
    # научен двум интерпретациям (PR 11), схема 2 читается как одна, классическая.
    warnings = []
    if schema != MIN_SCHEMA:
        warnings.append("schema: пакет схемы %s — стороны читаются как back/front/left/right; "
                        "две интерпретации для Южного полушария ещё не поддерживаются" % schema)
    algo = pack.get("algo") or {}
    for name, minimum in MIN_ALGO.items():
        have = _version_tuple(algo.get(name))
        if have < minimum:
            warnings.append("stale_algo: пакет собран %s %s, навык ждёт ≥ %s — числа могли "
                            "считаться по старым правилам" % (
                                name, ".".join(map(str, have)), ".".join(map(str, minimum))))
    return warnings


def landform_data(pack: dict, *, annual: int | None = None, tz: float = 8.0,
                  feixing_fn=None) -> dict:
    """Свести пакет участка в структуру 龍穴砂水向 + карта звёзд.

    Пакет — `site_pack.json` схемы `site_pack/1` из vector-geo-site. Отсутствующие поля
    остаются None: модуль не подставляет значения по умолчанию (правило П1).
    """
    version_warnings = check_pack_versions(pack)
    orientation = pack.get("orientation") or {}
    facing = _num(orientation.get("facing_true_deg"))
    chart_year = _num(_get(pack, "chart_year", "value"))
    year = int(chart_year) if chart_year else None

    chart = None
    chart_error = None
    if feixing_fn is None:
        chart_error = "расчёт звёзд не передан: вызовите из fengshui_bazi_calc.py"
    elif facing is None or year is None:
        chart_error = "нет оси или года застройки в пакете"
    else:
        chart = feixing_fn(facing, None, year, annual, tz)

    sectors = pack.get("sectors") or []
    rings = {}
    for sector in sectors:
        name = sector.get("mountain")
        if not name:
            continue
        for ring in sector.get("rings") or []:
            lo, hi = (ring.get("r_km") or [None, None])[:2]
            if lo is None:
                continue
            rings.setdefault((lo, hi), {})[name] = {
                "max_rel_elev_m": _num(ring.get("max_rel_elev_m")),
                "mean_rel_elev_m": _num(ring.get("mean_rel_elev_m")),
                "horizon_deg": _num(ring.get("horizon_deg")),
                "hill_share": _num(ring.get("hill_share")),
                "water_share": _num(ring.get("water_share")),
            }

    spirits = _normalize_spirits(pack.get("four_spirits") or {})
    vein = pack.get("dragon_vein") or {}
    point = pack.get("point") or {}
    water = pack.get("water") or []

    warnings: list[str] = list(version_warnings)
    checks: list[dict] = []

    def check(code: str, text: str, confidence: str = "high", canon: str | None = None):
        checks.append({"code": code, "text": text, "confidence": confidence, "canon": canon})

    # --- склонение и ветер (этап 4) ---
    climate = {}
    declination = _num(orientation.get("declination_deg"))
    if declination is not None:
        climate["declination_deg"] = declination
        climate["facing_mag_deg"] = _num(orientation.get("facing_mag_deg"))
        check("MAGNETIC", "истинный азимут %s°, компасный %s° (склонение %s°%s)" % (
            orientation.get("facing_true_deg"), climate["facing_mag_deg"],
            abs(declination), " в.д." if declination >= 0 else " з.д."),
            canon="磁偏角 — компас ≠ истинный север")
    exposure = pack.get("exposure") or {}
    wind = {k: exposure.get(k) for k in (
        "wind_prevailing_deg", "wind_prevailing_mountain", "wind_speed_ms",
        "wind_calm_share", "wind_days", "wind_seasonal", "wind_source")
        if exposure.get(k) is not None}
    if wind:
        climate["wind"] = wind
        seasonal = wind.get("wind_seasonal") or {}
        winter = (seasonal.get("winter") or {}).get("prevailing_from_deg")
        summer = (seasonal.get("summer") or {}).get("prevailing_from_deg")
        check("WIND", "преобладающий ветер: %s (%s°), %s м/с, штилей %s%s" % (
            _mountain_ru(wind.get("wind_prevailing_mountain")), wind.get("wind_prevailing_deg"),
            wind.get("wind_speed_ms"), wind.get("wind_calm_share"),
            ("; зима %s°, лето %s°" % (winter, summer)) if winter is not None and summer is not None else ""),
            canon="風 — 凹风 (ветер в фасад) считается по горе ветра против горы фасада")
        if wind.get("wind_prevailing_mountain") and orientation.get("facing_mountain"):
            if wind["wind_prevailing_mountain"] == orientation["facing_mountain"]:
                warnings.append("凹风: преобладающий ветер дует в фасад (гора ветра совпадает "
                                "с горой фасада) — фасад не защищён")
    elif pack.get("algo", {}).get("climate"):
        warnings.append("ветер: пакет собран с climate, но поля ветра пусты — смотрите "
                        "quality.warnings пакета")

    # --- ось ---
    source = orientation.get("source")
    confidence = orientation.get("confidence")
    if confidence in {"low", None}:
        warnings.append("orientation: %s — ось предварительная, карту звёзд считать нельзя "
                        "как окончательную" % (source or "источник не указан"))
        check("ORIENT-WEAK", "ось участка: %s, уверенность %s" % (_mountain_ru(orientation.get("facing_mountain")),
                                                                  confidence or "нет"),
              confidence="low", canon="向 — ось задаёт всю карту 飛星")
    else:
        check("ORIENT", "фасад %s, сидячая %s (%s)" % (
            _mountain_ru(orientation.get("facing_mountain")),
            _mountain_ru(orientation.get("sitting_mountain")), source or "?"),
            canon="向 / 坐")

    # --- год карты и период (R3) ---
    year_source = _get(pack, "chart_year", "source")
    if year is not None:
        period_built = chart.get("period") if chart else None
        check("YEAR", "карта построена по году %s → период %s (источник года: %s). "
                      "Текущий период — %s (%s–%s)" % (
                          year, period_built, year_source or "не указан",
                          CURRENT_PERIOD[0], CURRENT_PERIOD[1], CURRENT_PERIOD[2]),
              canon="元运 — период задаёт карту 飛星")
        if period_built is not None and period_built != CURRENT_PERIOD[0]:
            check("YEAR-GAP", "звёзды карты относятся к периоду постройки %s; оценку 旺/衰 "
                              "на текущий период %s нужно давать отдельно" % (
                                  period_built, CURRENT_PERIOD[0]),
                  confidence="medium", canon="飞星: карта здания ≠ текущие звёзды")
    else:
        warnings.append("год постройки не задан — карта на текущий период, а не натальная "
                        "карта здания")
        check("YEAR-MISSING", "карта построена на текущий период %s (%s–%s)" % (
            CURRENT_PERIOD[0], CURRENT_PERIOD[1], CURRENT_PERIOD[2]),
              confidence="low", canon="元运")

    # --- точка ---
    if point:
        check("SITE", "участок: высота %s м, уклон %s°, форма %s" % (
            point.get("elev_m"), point.get("slope_deg"), point.get("shape") or "—"),
            confidence="medium" if point.get("shape") == "гребень" else "high", canon="穴")

    # --- рельеф: 24 горы ---
    for (lo, hi), by_mountain in sorted(rings.items(), key=lambda kv: (kv[0][0] or 0)):
        top = sorted((v["max_rel_elev_m"] or -1e9, k) for k, v in by_mountain.items())[-3:][::-1]
        if not top:
            continue
        items = ", ".join("%s %+.0f м" % (_mountain_ru(k), v) for v, k in top if v > -1e8)
        check("RING-%g-%g" % (lo, hi), "кольцо %g–%g км, самые высокие: %s" % (lo, hi, items),
              canon="砂 — охрана вокруг участка")

    # --- четыре духа ---
    if spirits:
        tortoise = _num(_get(spirits, "tortoise", "rel_elev_m"))
        bird = _num(_get(spirits, "bird", "rel_elev_m"))
        dragon = _num(_get(spirits, "dragon", "rel_elev_m"))
        tiger = _num(_get(spirits, "tiger", "rel_elev_m"))
        diff = _num(spirits.get("dragon_vs_tiger"))
        for key, value in (("tortoise", tortoise), ("bird", bird), ("dragon", dragon), ("tiger", tiger)):
            if value is not None:
                check("SPIRIT-%s" % key.upper(), "%s: %+.0f м" % (SPIRIT_RU[key], value),
                      canon="四神 — черепаха, птица, дракон, тигр")
        if tortoise is not None and bird is not None:
            if tortoise > bird + 5:
                check("SPIRIT-BACK-STRONG", "спина выше фасада на %.0f м — опора сзади" % (tortoise - bird),
                      canon="玄武 выше 朱雀")
            elif bird > tortoise + 5:
                check("SPIRIT-FRONT-STRONG", "фасад выше спины на %.0f м — опоры сзади нет" % (bird - tortoise),
                      confidence="medium", canon="朱雀 выше 玄武")
        if diff is not None:
            side = "дракон выше" if diff > 0 else "тигр выше"
            check("SPIRIT-SIDES", "%s на %.0f м (дракон %+.0f / тигр %+.0f)" % (side, abs(diff), dragon, tiger),
                  confidence="medium", canon="青龍 / 白虎")

    # --- драконья жила ---
    if vein:
        check("VEIN", "жила: %.1f км, подъём %+.0f м, изгибов %s, сёдел %s, живая: %s" % (
            _num(vein.get("length_km")) or 0, _num(vein.get("drop_m")) or 0,
            vein.get("bends"), vein.get("saddles"), "да" if vein.get("alive") else "нет"),
            confidence="medium", canon="龍 — жила приходит к точке")

    # --- вода (R2 п. 4, E-019): каждый объект — ровно в одном разделе ---
    # Вода делится на три раздела по данным пакета: видимые русла (來水/去水), подземные (暗水)
    # и водоёмы. До 7.0.0 навык смотрел только на `kind` и показывал трубу и в 來水, и в 暗水.
    courses = [w for w in water if w.get("kind") in AQUATIC_KINDS]
    modern = any("geom" in w for w in water)
    if modern:
        areas = [w for w in water
                 if _is_area(w) and (_num(w.get("area_m2")) or 0.0) >= AREA_MIN_M2]
        # Док-канал (`dock_channel_of`) — не русло: он показывается вместе с контуром
        line_water = [w for w in courses if not _is_area(w) and not w.get("dock_channel_of")]
        streaming = [w for w in line_water
                     if w.get("visible") is not False and _hidden_share(w) < 0.8]
        hidden = [w for w in line_water
                  if w.get("visible") is False or _hidden_share(w) >= 0.8]
    else:
        # R8: пакет до water 7.0.0 — полей `geom` и `visible` нет; читаем по старой логике
        # и говорим об этом прямо, а не делаем вид, что разделы проверены.
        warnings.append("stale_algo: в пакете нет полей geom и visible — вода показана по "
                        "старой логике; пересоберите пакет в vector-geo-site (water ≥ 7.0.0)")
        areas = []
        streaming = list(courses)
        hidden = [w for w in water if w.get("kind") == "culvert"]
    rivers = streaming

    channels: dict[str, list[str]] = {}
    for item in water:
        owner = item.get("dock_channel_of")
        if owner:
            channels.setdefault(owner, []).append(item.get("name") or str(item.get("id")))

    reported: set[str] = set()   # id объектов, реально попавших в отчёт
    seen_ids: set[str] = set()

    def _once(item: dict) -> bool:
        """Каждый объект в отчёте ровно один раз: разделы не пересекаются по данным."""
        key = str(item.get("id") or item.get("name") or "?")
        if key in seen_ids:
            return False
        seen_ids.add(key)
        return True

    # 來水 / 去水 — только видимые русла
    shown = 0
    for item in sorted(streaming, key=lambda w: w.get("nearest_m") or 1e9):
        if shown >= 5 or not _once(item):
            continue
        shown += 1
        reported.add(str(item.get("id")))
        name = item.get("name") or item.get("id")
        tid = item.get("tidal")
        tide_txt = "приливная" if tid is True else ("неприливная" if tid is False else "приливность неизвестна")
        bend = item.get("bend") or item.get("bend_kind") or "—"
        loop = item.get("loop") or {}
        loop_txt = ""
        if loop:
            ratio = _num(loop.get("ratio"))
            position = LOOP_POSITION_RU.get(item.get("site_position") or loop.get("site_position") or "", "")
            loop_conf = loop.get("confidence") or "unknown"
            loop_txt = ", петля (ratio %s%s, уверенность %s)" % (
                "%.2f" % ratio if ratio is not None else "?",
                ", " + position if position else "", loop_conf)
            if loop_conf == "low":
                # E-021: пограничную петлю не выдаём за 玉帶 или 反弓 наверняка
                warnings.append("%s: петля с запасом у порога (margin %s) — вывод о петле с оговоркой"
                                % (name or "?", loop.get("margin")))
        reason = item.get("same_mountain_reason")
        same_txt = ""
        if reason and item.get("in_mountain") and item.get("in_mountain") == item.get("out_mountain"):
            same_txt = ", вход и выход в одной горе: %s" % reason
        partial = ""
        share = _hidden_share(item)
        if modern and 0.2 <= share < 0.8:
            partial = ", частично в трубе (%d %%), видимая часть — гора %s" % (
                round(share * 100), _mountain_ru(item.get("out_mountain")))
        if item.get("in_mountain") is None and item.get("out_mountain") is None:
            # Пара 來水/去水 не измерена: внутри круга 2 км от русла нет ни метра
            # (в пакете in_mountain и out_mountain отсутствуют). Даём сторону и расстояние.
            text = "%s: %s м, сторона %s, вход и выход не измерены (вне круга 2 км)%s" % (
                name, item.get("nearest_m"), _mountain_ru(item.get("nearest_mountain")), partial)
        else:
            text = "%s: %s м, вход %s, выход %s, %s, %s%s%s%s" % (
                name, item.get("nearest_m"), _mountain_ru(item.get("in_mountain")),
                _mountain_ru(item.get("out_mountain")), bend, tide_txt, loop_txt, same_txt,
                partial)
        check("WATER-%s" % (name or "?"), text,
              confidence=item.get("flow_confidence") or "нет замера", canon="水 — 來水 / 去水")
        mouth = item.get("water_mouth") or {}
        if mouth:
            closing = mouth.get("closure_index")
            if closing is None:
                mouth_txt = "врата открыты: %s" % (mouth.get("closure_reason") or "нет замера")
                mouth_conf = "low"
            else:
                mouth_txt = "врата %s: замкнутость %.2f, ширина %s м" % (
                    _mountain_ru(mouth.get("mountain")), closing, mouth.get("width_m"))
                mouth_conf = mouth.get("closure_confidence") or "unknown"
                if mouth_conf == "unknown":
                    warnings.append("%s: пакет не передал уверенность врат (closure_confidence) — "
                                    "число есть, доверия к нему нет" % (name or "?"))
            if mouth.get("width_capped"):
                warnings.append("%s: замер врат упёрся в предел (сторон: %s) — число неполное"
                                % (name, mouth.get("capped_sides")))
            check("GATE-%s" % (name or "?"), mouth_txt, confidence=mouth_conf, canon="水口")

    # 暗水 — подземная вода, по строке на объект
    shown = 0
    for item in sorted(hidden, key=lambda w: w.get("nearest_m") or 1e9):
        if shown >= 5 or not _once(item):
            continue
        shown += 1
        reported.add(str(item.get("id")))
        name = item.get("name") or item.get("id")
        outfall = item.get("culvert_outfall")
        extra = ", выход на поверхность: %s" % _mountain_ru(outfall) if outfall else ""
        mountain = item.get("nearest_mountain") or item.get("out_mountain")
        check("HIDDEN-%s" % (name or "?"),
              "%s: %s м, %s%s" % (name, item.get("nearest_m"), _mountain_ru(mountain), extra),
              confidence="medium", canon="暗水")

    # водоёмы — отдельный раздел: у контура нет входа и выхода (E-018)
    shown = 0
    # Сначала доки и бассейны: это именованная вода, которую читает толкователь; прудов в
    # радиусе десятки, и по одному расстоянию они вытесняют бассейн из отчёта.
    # Доки и бассейны первыми, дальше — по площади: с water 8.0.0 в пакете появились
    # поверхности рек (берега Темзы), и по расстоянию они вытеснялись прудами соседнего двора.
    def body_rank(w: dict) -> tuple[int, float]:
        """Поверхность реки важнее дока, док важнее пруда; внутри группы — по площади."""
        kind = 0 if w.get("riverbank_of") else (1 if w.get("kind") in {"dock", "sea"} else 2)
        return (kind, -(w.get("area_m2") or 0.0))

    seen_banks: set[str] = set()
    for item in sorted(areas, key=body_rank):
        bank = str(item.get("riverbank_of") or "")
        if bank and bank in seen_banks:
            # поверхность одной реки в OSM разрезана мостами: в отчёт идёт ближайший кусок,
            # остальные остаются в water.geojson, а не занимают строки отчёта
            reported.add(str(item.get("id")))
            continue
        if shown >= 5 or not _once(item):
            continue
        if bank:
            seen_banks.add(bank)
        shown += 1
        reported.add(str(item.get("id")))
        name = item.get("name") or item.get("id")
        # поверхность реки — не пруд: в пакете у неё `riverbank_of`, и в отчёте она так и
        # называется, иначе «River Thames, площадь 2 429 113 м²» читается как озеро
        label = ("берег реки: %s" % name) if item.get("riverbank_of") else name
        inside = item.get("site_inside")
        inside_txt = ("участок на воде" if inside is True
                      else ("рядом, вне контура" if inside is False else "не измерено"))
        area_m2 = _num(item.get("area_m2"))
        area_txt = ", площадь %s м²" % (("%.0f" % area_m2) if area_m2 is not None else "—")
        channel_txt = ", канал внутри контура" if channels.get(str(item.get("id"))) else ""
        check("WATERBODY-%s" % (name or "?"),
              "%s: %s м, %s, %s%s%s" % (label, item.get("nearest_m"),
                                        _mountain_ru(item.get("nearest_mountain")), inside_txt,
                                        area_txt, channel_txt),
              confidence="high", canon="水 — водоёмы")

    # --- внешняя форма против формата (R3 п. 4) ---
    if chart and "旺山旺向" in str(chart.get("format") or ""):
        tortoise_m = _num(_get(spirits, "tortoise", "rel_elev_m"))
        bird_m = _num(_get(spirits, "bird", "rel_elev_m"))
        nearest_water = sorted(rivers, key=lambda w: w.get("nearest_m") or 1e9)
        water_front = None
        if nearest_water:
            item = nearest_water[0]
            water_front = item.get("in_mountain") or item.get("out_mountain")
        problems = []
        if tortoise_m is None or bird_m is None:
            problems.append("высоты четырёх духов не переданы пакетом")
        elif tortoise_m <= bird_m + 5:
            problems.append("гора за спиной не выше фасада (спина %+.0f, фасад %+.0f м)" % (
                tortoise_m, bird_m))
        if water_front is None:
            problems.append("вода перед фасадом не найдена в пакете")
        else:
            # вода должна быть со стороны фасада, а не за спиной
            facing_az = _num(orientation.get("facing_true_deg"))
            water_az = MOUNTAIN_CENTER.get(water_front)
            if facing_az is not None and water_az is not None:
                diff = abs((facing_az - water_az + 180) % 360 - 180)
                if diff > 90:
                    problems.append("ближайшая вода %s (%s) стоит за спиной, а не перед фасадом"
                                    % (_mountain_ru(water_front), water_front))
        if problems:
            check("FORMAT-CONFLICT", "формат 旺山旺向 требует горы за спиной и воды перед фасадом, "
                                     "а внешняя форма этому противоречит: " + "; ".join(problems),
                  confidence="low", canon="旺山旺向 проверяется внешней формой")
        else:
            check("FORMAT-CHECK", "формат 旺山旺向 согласуется с внешней формой: спина %+.0f, "
                                  "фасад %+.0f м, вода %s" % (tortoise_m, bird_m,
                                                             _mountain_ru(water_front)),
                  canon="旺山旺向")

    # --- карта звёзд ---
    if chart:
        grid = chart.get("grid") or {}
        fac_m = chart.get("facing")
        sit_m = chart.get("sitting")
        pal_fac = next((p for p, v in (grid.items() if isinstance(grid, dict) else [])), None)
        check("FLYING", "период %s, формат %s, фасад %s, сидячая %s" % (
            chart.get("period"), chart.get("format"),
            _mountain_ru(fac_m), _mountain_ru(sit_m)), canon="飛星")

    # --- поля с низкой уверенностью ---
    low_fields = []
    if confidence == "low":
        low_fields.append("orientation")
    far_low = 0
    for item in water:
        if item.get("flow_confidence") == "low" and str(item.get("id")) not in reported:
            far_low += 1
        if item.get("flow_confidence") == "low" and str(item.get("id")) in reported:
            low_fields.append("water.flow:%s" % (item.get("name") or item.get("id")))
        if _get(item, "water_mouth", "closure_confidence") == "low":
            low_fields.append("water.closure:%s" % (item.get("name") or item.get("id")))
    for item in water:
        if (item.get("flow_chosen") and not item.get("flow_confidence")
                and item.get("in_mountain") is not None):
            warnings.append("water.flow:%s — правило течения без уверенности"
                            % (item.get("name") or item.get("id")))
    if low_fields:
        warnings.append("поля с уверенностью low: " + ", ".join(sorted(set(low_fields))))
    if far_low:
        # В пакете воды больше, чем в отчёте: дальние водотоки с низкой уверенностью не
        # перечисляем поимённо, иначе оговорки перерастают сам отчёт.
        warnings.append("ещё %d водоток(а) с низкой уверенностью за пределами отчёта — в пакете"
                        % far_low)

    return {
        "schema": pack.get("schema"),
        "algo": pack.get("algo"),
        "site": pack.get("site"),
        "orientation": orientation,
        "climate": climate,
        "chart_year": pack.get("chart_year"),
        "chart": chart,
        "chart_error": chart_error,
        "versions": {"min": {k: ".".join(map(str, v)) for k, v in MIN_ALGO.items()},
                     "pack": pack.get("algo")},
        "checks": checks,
        "warnings": warnings,
        "vein": vein or None,
        "spirits": spirits or None,
        "water": [
            {k: item.get(k) for k in ("id", "name", "kind", "nearest_m", "in_mountain", "out_mountain",
                                      "bend", "bend_kind", "tidal", "loop", "water_mouth",
                                      "site_position", "visible", "hidden_share")}
            for item in sorted(rivers, key=lambda w: w.get("nearest_m") or 1e9)[:5]
        ],
        # E-019: подземная вода и водоёмы — отдельно от 來水/去水, без повторов
        "water_hidden": [
            {k: item.get(k) for k in ("id", "name", "kind", "nearest_m", "nearest_mountain",
                                      "hidden_share", "visible", "culvert_outfall")}
            for item in sorted(hidden, key=lambda w: w.get("nearest_m") or 1e9)[:5]
        ],
        "water_bodies": [
            {k: item.get(k) for k in ("id", "name", "kind", "nearest_m", "nearest_mountain",
                                      "area_m2", "site_inside", "riverbank_of")}
            for item in sorted(areas, key=lambda w: (0 if w.get("kind") in {"dock", "sea"} else 1,
                                                     w.get("nearest_m") or 1e9))[:5]
        ],
        "summary": pack.get("summary"),
        "files": pack.get("files"),
        "attribution": pack.get("attribution"),
    }


def landform_markdown(data: dict) -> str:
    """Markdown-отчёт по данным landform_data: измерения, канон, оговорки."""
    lines: list[str] = []
    site = data.get("site") or {}
    orientation = data.get("orientation") or {}
    lines.append("# Участок: форма, вода, ориентация")
    lines.append("")
    lines.append("Координаты: %s, %s · высота %s м · зона UTM %s" % (
        site.get("lat"), site.get("lon"), site.get("elev_m"), site.get("utm_epsg")))
    lines.append("")
    lines.append("## 向 — ориентация")
    lines.append("")
    lines.append("- фасад: %s, сидячая: %s" % (_mountain_ru(orientation.get("facing_mountain")),
                                                _mountain_ru(orientation.get("sitting_mountain"))))
    lines.append("- азимут: %s°, источник: %s, уверенность: %s" % (
        orientation.get("facing_true_deg"), orientation.get("source"), orientation.get("confidence")))
    climate = data.get("climate") or {}
    if climate.get("declination_deg") is not None:
        lines.append("- компасный азимут: %s° (склонение %s°)" % (
            climate.get("facing_mag_deg"), climate.get("declination_deg")))
    wind = climate.get("wind") or {}
    if wind:
        lines.append("- ветер: %s (%s°), %s м/с, дней в выборке %s" % (
            _mountain_ru(wind.get("wind_prevailing_mountain")), wind.get("wind_prevailing_deg"),
            wind.get("wind_speed_ms"), wind.get("wind_days")))
    chart = data.get("chart")
    if chart:
        lines.append("- период %s, формат: %s" % (chart.get("period"), chart.get("format")))
        grid = chart.get("grid_ru") or {}
        if grid:
            lines.append("")
            lines.append("| Дворец | гора / период / вода |")
            lines.append("|---|---|")
            for palace, stars in grid.items():
                lines.append("| %s | %s / %s / %s |" % (palace, stars[0], stars[1], stars[2]))
    else:
        lines.append("- карта звёзд не рассчитана: %s" % (data.get("chart_error") or "нет данных"))
    lines.append("")

    lines.append("## 砂 — охрана и горы")
    lines.append("")
    for check in data.get("checks") or []:
        if check["code"].startswith(("SPIRIT", "RING", "SITE", "VEIN")):
            lines.append("- **%s.** %s (%s)" % (check["canon"] or "—", check["text"], check["confidence"]))
    lines.append("")

    lines.append("## 水 — реки и врата")
    lines.append("")
    water_checks = [c for c in data.get("checks") or []
                    if c["code"].startswith(("WATER-", "GATE-"))]
    hidden_checks = [c for c in data.get("checks") or [] if c["code"].startswith("HIDDEN-")]
    body_checks = [c for c in data.get("checks") or [] if c["code"].startswith("WATERBODY-")]

    lines.append("### 來水 / 去水")
    lines.append("")
    for check in water_checks:
        lines.append("- **%s.** %s (%s)" % (check["canon"] or "—", check["text"], check["confidence"]))
    if not water_checks:
        lines.append("- видимых русел в пакете нет")
    lines.append("")
    if hidden_checks:
        lines.append("### 暗水")
        lines.append("")
        for check in hidden_checks:
            lines.append("- **%s.** %s (%s)" % (check["canon"] or "—", check["text"], check["confidence"]))
        lines.append("")
    if body_checks:
        lines.append("### Водоёмы")
        lines.append("")
        for check in body_checks:
            lines.append("- **%s.** %s (%s)" % (check["canon"] or "—", check["text"], check["confidence"]))
        lines.append("")

    lines.append("## Оговорки")
    lines.append("")
    if data.get("warnings"):
        for warning in data["warnings"]:
            lines.append("- %s" % warning)
    else:
        lines.append("- оговорок нет")
    lines.append("")
    algo = data.get("algo") or {}
    if algo:
        lines.append("Версии расчёта: " + ", ".join("%s %s" % (k, v) for k, v in algo.items() if v))
    files = data.get("files") or {}
    if files.get("water_geojson"):
        lines.append("Полный набор воды: %s" % files["water_geojson"])
    attribution = data.get("attribution") or []
    if attribution:
        lines.append("")
        lines.append(" ".join(attribution))
    return "\n".join(lines)


def load_pack(path: str | Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))
