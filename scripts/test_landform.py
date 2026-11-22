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
             "nearest_m": 120.0, "in_mountain": "乾", "out_mountain": "巽"},
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

    # 4. Скрытая вода попадает в отчёт
    hidden = [c for c in data["checks"] if c["code"] == "HIDDEN"]
    check("скрытая вода", len(hidden), 1)

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

    # 10a. R8: старая версия расчёта — предупреждение, но отчёт строится
    old = base_pack(algo={"water": "3.1.0", "terrain": "2.0.0", "pack": "1.1.0"})
    data_old = L.landform_data(old, feixing_fn=feixing)
    check("старый пакет: отчёт есть", data_old["chart"] is not None, True)
    check("старый пакет: stale_algo",
          any(w.startswith("stale_algo") for w in data_old["warnings"]), True)

    # 10b. R8: чужая схема — отказ с понятным сообщением
    wrong = base_pack(schema="site_pack/2")
    try:
        L.landform_data(wrong, feixing_fn=feixing)
        refused = False
    except ValueError:
        refused = True
    check("чужая схема: отказ", refused, True)

    # 10c. R3: год и текущий период в отчёте
    year_text = " ".join(c["text"] for c in data["checks"] if c["code"].startswith("YEAR"))
    check("строка про год карты", "период 8" in year_text, True)
    check("строка про текущий период 9", "Текущий период — 9" in year_text, True)
    check("пояснение про разрыв периодов",
          any(c["code"] == "YEAR-GAP" for c in data["checks"]), True)

    # 10d. R3: пакет без года — карта на текущий период и оговорка
    no_year = base_pack(chart_year={"value": None, "source": None})
    data_ny = L.landform_data(no_year, feixing_fn=feixing)
    check("нет года: оговорка",
          any("год постройки не задан" in w for w in data_ny["warnings"]), True)

    # 10e. R3: формат 旺山旺向 проверяется внешней формой — вода за спиной
    conflict = base_pack()
    # фасад остаётся 133° (巽): при годе 2018 это даёт формат 旺山旺向
    conflict["four_spirits"] = {"tortoise": {"rel_elev_m": 30.0},
                                "bird": {"rel_elev_m": 5.0},
                                "dragon": {"rel_elev_m": 10.0}, "tiger": {"rel_elev_m": 8.0},
                                "dragon_vs_tiger": 2.0}
    conflict["water"][0]["in_mountain"] = "乾"                 # вода за спиной (сидячая 乾)
    data_cf = L.landform_data(conflict, feixing_fn=feixing)
    check("формат: противоречие с водой за спиной",
          any(c["code"] == "FORMAT-CONFLICT" for c in data_cf["checks"]), True)

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
