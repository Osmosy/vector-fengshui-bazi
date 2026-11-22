"""landform: чтение пакета vector-geo-site и сведение 龍穴砂水向 с картой звёзд.

Вставляется в scripts/fengshui_bazi_calc.py (только стандартная библиотека).
Правило: пакет измеряет, навык читает. Поля с уверенностью low не дают категоричных выводов.
"""

from __future__ import annotations

import json
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


def _mountain_ru(name: str | None) -> str:
    if not name:
        return "—"
    return "%s (%s)" % (name, MOUNTAIN_RU.get(name, "?")) if name in MOUNTAIN_CENTER else str(name)


def landform_data(pack: dict, *, annual: int | None = None, tz: float = 8.0,
                  feixing_fn=None) -> dict:
    """Свести пакет участка в структуру 龍穴砂水向 + карта звёзд.

    Пакет — `site_pack.json` схемы `site_pack/1` из vector-geo-site. Отсутствующие поля
    остаются None: модуль не подставляет значения по умолчанию (правило П1).
    """
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

    spirits = pack.get("four_spirits") or {}
    vein = pack.get("dragon_vein") or {}
    point = pack.get("point") or {}
    water = pack.get("water") or []

    warnings: list[str] = []
    checks: list[dict] = []

    def check(code: str, text: str, confidence: str = "high", canon: str | None = None):
        checks.append({"code": code, "text": text, "confidence": confidence, "canon": canon})

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

    # --- вода ---
    rivers = [w for w in water if w.get("kind") in {"river", "stream", "canal", "culvert"}]
    for item in sorted(rivers, key=lambda w: w.get("nearest_m") or 1e9)[:5]:
        name = item.get("name") or item.get("id")
        tid = item.get("tidal")
        tide_txt = "приливная" if tid is True else ("неприливная" if tid is False else "приливность неизвестна")
        bend = item.get("bend") or item.get("bend_kind") or "—"
        loop = item.get("loop") or {}
        loop_txt = ""
        if loop:
            loop_txt = ", петля (ratio %.1f%s)" % (_num(loop.get("ratio")) or 0,
                                                   ", участок внутри" if loop.get("site_inside") else "")
        check("WATER-%s" % (name or "?"),
              "%s: %s м, вход %s, выход %s, %s, %s%s" % (
                  name, item.get("nearest_m"), _mountain_ru(item.get("in_mountain")),
                  _mountain_ru(item.get("out_mountain")), bend, tide_txt, loop_txt),
              confidence=item.get("flow_confidence") or "unknown", canon="水 — 來水 / 去水")
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

    # --- скрытая вода ---
    hidden = [w for w in water if w.get("kind") == "culvert"]
    if hidden:
        names = ", ".join((w.get("name") or w.get("id") or "?") for w in hidden[:5])
        check("HIDDEN", "скрытая вода в трубе: %s" % names, confidence="medium", canon="暗水")

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
    for item in water:
        if item.get("flow_confidence") == "low":
            low_fields.append("water.flow:%s" % (item.get("name") or item.get("id")))
        if _get(item, "water_mouth", "closure_confidence") == "low":
            low_fields.append("water.closure:%s" % (item.get("name") or item.get("id")))
    for item in water:
        if item.get("flow_chosen") and not item.get("flow_confidence"):
            warnings.append("water.flow:%s — правило течения без уверенности"
                            % (item.get("name") or item.get("id")))
    if low_fields:
        warnings.append("поля с уверенностью low: " + ", ".join(sorted(set(low_fields))))

    return {
        "schema": pack.get("schema"),
        "algo": pack.get("algo"),
        "site": pack.get("site"),
        "orientation": orientation,
        "chart_year": pack.get("chart_year"),
        "chart": chart,
        "chart_error": chart_error,
        "checks": checks,
        "warnings": warnings,
        "vein": vein or None,
        "spirits": spirits or None,
        "water": [
            {k: item.get(k) for k in ("name", "kind", "nearest_m", "in_mountain", "out_mountain",
                                      "bend", "bend_kind", "tidal", "loop", "water_mouth")}
            for item in sorted(rivers, key=lambda w: w.get("nearest_m") or 1e9)[:5]
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
    for check in data.get("checks") or []:
        if check["code"].startswith(("WATER", "GATE", "HIDDEN")):
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
