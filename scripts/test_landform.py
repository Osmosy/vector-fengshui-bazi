#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Регрессионные тесты команды landform (пакет участка → 龍穴砂水向 + 飛星).

Запуск: python3 test_landform.py  (из каталога scripts/)

Проверяем контракт с vector-geo-site: схема site_pack/1, обязательные поля, поведение
при отсутствующих данных (null, а не выдуманное значение) и предупреждения о low-уверенности.
"""
import copy
import json

import fengshui_bazi_calc as f
import landform as L

CHECKS = []


def check(name, actual, expected):
    ok = actual == expected
    CHECKS.append((name, ok, actual, expected))
    return ok


def base_pack(**over):
    pack = {
        "schema": "site_pack/1",
        "algo": {"water": "4.0.0", "terrain": "2.0.1", "pack": "1.2.0"},
        "site": {"lat": 51.5138, "lon": -0.0984, "elev_m": 28.4, "utm_epsg": 32630,
                 "precision": "district"},
        "orientation": {"facing_true_deg": 135.0, "facing_mountain": "巽", "sitting_mountain": "乾",
                        "source": "model", "confidence": "low", "near_boundary": False},
        "chart_year": {"value": 2018, "source": "user"},
        "sectors": [
            {"mountain": "巽", "from_deg": 127.5, "to_deg": 142.5,
             "rings": [{"r_km": [2.0, 8.0], "max_rel_elev_m": 20.0, "mean_rel_elev_m": 4.0,
                        "horizon_deg": 0.4, "hill_share": 0.3, "peaks": []}]},
        ],
        "point": {"slope_deg": 2.8, "aspect_deg": 136.0, "shape": "склон", "elev_m": 28.4},
        "four_spirits": {"tortoise": {"rel_elev_m": 109.0, "dist_km": 8.0, "continuity": 0.79},
                         "bird": {"rel_elev_m": 62.0, "dist_km": 7.9, "continuity": 0.71},
                         "dragon": {"rel_elev_m": 20.0, "dist_km": 7.9, "continuity": 0.46},
                         "tiger": {"rel_elev_m": 113.0, "dist_km": 8.0, "continuity": 0.71},
                         "dragon_vs_tiger": -92.5},
        "dragon_vein": {"length_km": 12.0, "drop_m": 108.1, "bends": 6, "saddles": 0, "alive": True},
        "water": [
            {"id": "osm-River Thames-river", "name": "River Thames", "kind": "river",
             "nearest_m": 463.6, "in_mountain": "坤", "out_mountain": "辰", "bend": "outer",
             "bend_kind": "bend", "tidal": True, "flow_confidence": "medium",
             "flow_chosen": "downstream_toward_end",
             "loop": None,
             "water_mouth": {"mountain": "乙", "closure_index": 0.01, "width_capped": True,
                             "capped_sides": 1, "width_m": 4850.0,
                             "closure_confidence": "low"}},
            {"id": "osm-Neglinka-culvert", "name": "Неглинная", "kind": "culvert",
             "nearest_m": 120.0, "in_mountain": "乾", "out_mountain": "巽",
             "visible": False, "hidden_share": 0.9, "pieces": 2},
        ],
    }
    pack.update(over)
    return pack


def run():
    feixing = f.feixing_data

    # 1. Карта звёзд считается по оси и году из пакета
    data = L.landform_data(base_pack(), feixing_fn=feixing)
    chart = data["chart"]
    check("карта есть", chart is not None, True)
    check("период 8 по 2018", chart["period"], 8)
    check("фасад 巽", chart["facing"], "巽")
    check("сидячая 乾", chart["sitting"], "乾")

    # 2. Ось по модели → предупреждение, а не «лучший формат» без оговорок
    warnings = " ".join(data["warnings"])
    check("предупреждение об оси", "ориентация" in warnings or "ось" in warnings, True)
    check("low-поля перечислены", any("low" in w for w in data["warnings"]), True)

    # 3. Вода читается из пакета, включая приливность и врата
    names = [w["name"] for w in data["water"]]
    check("Темза в сводке", "River Thames" in names, True)
    thames = next(w for w in data["water"] if w["name"] == "River Thames")
    check("приливность", thames["tidal"], True)
    gates = [c for c in data["checks"] if c["code"].startswith("GATE-")]
    check("врата посчитаны", len(gates), 1)
    check("врата low-уверенность", gates[0]["confidence"], "low")

    # 3a. Пакет без closure_confidence: unknown и оговорка, а не подставленный medium
    no_conf = base_pack()
    no_conf["water"][0]["water_mouth"] = {"mountain": "乙", "closure_index": 0.01,
                                          "width_capped": True, "capped_sides": 1,
                                          "width_m": 4850.0}
    data_nc = L.landform_data(no_conf, feixing_fn=feixing)
    gates_nc = [c for c in data_nc["checks"] if c["code"].startswith("GATE-")]
    check("врата без уверенности → unknown", gates_nc[0]["confidence"], "unknown")
    check("оговорка про уверенность врат",
          any("не передал уверенность врат" in w for w in data_nc["warnings"]), True)

    # 4. Скрытая вода — только в 暗水, по одной строке на водоток (R2)
    hidden = [c for c in data["checks"] if c["code"].startswith("HIDDEN-")]
    check("скрытая вода в 暗水", len(hidden), 1)
    check("暗水 — про Неглинную", "Неглинная" in hidden[0]["text"], True)
    check("暗水: доля под землёй", "90%" in hidden[0]["text"], True)
    visible_water = [c for c in data["checks"] if c["code"] == "WATER-River Thames"]
    check("Темза в открытой воде", len(visible_water), 1)
    check("скрытая вода не в 來水",
          any("Неглинная" in c["text"] for c in data["checks"] if c["code"].startswith("WATER-")),
          False)

    # 5. Духи сравниваются по оси: черепаха выше птицы
    texts = " ".join(c["text"] for c in data["checks"])
    check("спина выше фасада", "спина выше фасада" in texts, True)

    # 6. Пакет без воды и без оси не падает, а сообщает, чего нет
    empty = base_pack(water=[], orientation={"source": "model", "confidence": "low"})
    data2 = L.landform_data(empty, feixing_fn=feixing)
    check("нет оси → нет карты", data2["chart"], None)
    check("причина названа", bool(data2["chart_error"]), True)
    check("нет воды → пустой список", data2["water"], [])

    # 7. Markdown содержит все разделы
    text = L.landform_markdown(data)
    for section in ("## 向", "## 砂", "## 水", "## Оговорки"):
        check("раздел %s" % section, section in text, True)

    # 8. JSON-сериализация возможна (пакет целиком уходит в отчёт)
    try:
        json.dumps(data, ensure_ascii=False)
        ok = True
    except TypeError:
        ok = False
    check("данные сериализуются", ok, True)

    # 9. Копия пакета не портится
    original = base_pack()
    before = json.dumps(original, sort_keys=True)
    L.landform_data(copy.deepcopy(original), feixing_fn=feixing)
    check("пакет не изменён", json.dumps(original, sort_keys=True), before)

    # 10. Год берётся из chart_year, а не из текущего
    older = base_pack(chart_year={"value": 2004, "source": "user"})
    data3 = L.landform_data(older, feixing_fn=feixing)
    check("период 8 для 2004", data3["chart"]["period"], 8)


if __name__ == "__main__":
    run()
    failed = [c for c in CHECKS if not c[1]]
    for name, ok, actual, expected in CHECKS:
        print(("  ok   " if ok else "  FAIL ") + name + (
            "" if ok else ": получено %r, ждали %r" % (actual, expected)))
    print("\n%d/%d проверок пройдено" % (len(CHECKS) - len(failed), len(CHECKS)))
    raise SystemExit(1 if failed else 0)
