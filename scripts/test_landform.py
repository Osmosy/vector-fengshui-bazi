#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Регрессионные тесты команды landform (пакет участка → 龍穴砂水向 + 飛星).

Запуск: python3 test_landform.py  (из каталога scripts/)

Проверяем контракт с vector-geo-site: схема site_pack/1, обязательные поля, поведение
при отсутствующих данных (null, а не выдуманное значение) и предупреждения о low-уверенности.
"""
import copy
import json
import re
from pathlib import Path

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
             "geom": "line", "visible": True, "hidden_share": 0.0,
             "nearest_m": 463.6, "in_mountain": "坤", "out_mountain": "辰", "bend": "outer",
             "bend_kind": "bend", "tidal": True, "flow_confidence": "medium",
             "flow_chosen": "downstream_toward_end",
             "loop": None,
             "water_mouth": {"mountain": "乙", "closure_index": 0.01, "width_capped": True,
                             "capped_sides": 1, "width_m": 4850.0,
                             "closure_confidence": "low"}},
            {"id": "osm-Neglinka-culvert", "name": "Неглинная", "kind": "culvert",
             "geom": "line", "visible": False, "hidden_share": 1.0,
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
    hidden = [c for c in data["checks"] if c["code"].startswith("HIDDEN-")]
    check("скрытая вода", len(hidden), 1)
    check("скрытая вода: имя", "Неглинная" in hidden[0]["text"], True)
    check("труба не в 來水",
          any(c["code"] == "WATER-Неглинная" for c in data["checks"]), False)

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
    wrong = base_pack(schema="site_pack/3")
    try:
        L.landform_data(wrong, feixing_fn=feixing)
        refused = False
    except ValueError:
        refused = True
    check("чужая схема: отказ", refused, True)
    # 10b2. схема 2: читается, но с оговоркой, что две интерпретации ещё не сделаны
    s2 = base_pack(schema="site_pack/2")
    data_s2 = L.landform_data(s2, feixing_fn=feixing)
    check("схема 2: оговорка", any(w.startswith("schema:") for w in data_s2["warnings"]), True)

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



    # 11. Этап 4: склонение и ветер
    with_climate = base_pack()
    with_climate["algo"]["climate"] = "1.0.0"
    with_climate["orientation"].update({"declination_deg": 1.238, "facing_mag_deg": 133.8})
    with_climate["exposure"] = {"wind_prevailing_deg": 235.8, "wind_prevailing_mountain": "申",
                                "wind_speed_ms": 3.97, "wind_calm_share": 0.002, "wind_days": 3653,
                                "wind_seasonal": {"winter": {"prevailing_from_deg": 234.1},
                                                  "summer": {"prevailing_from_deg": 241.0}}}
    data_cl = L.landform_data(with_climate, feixing_fn=feixing)
    check("склонение: компасный азимут", data_cl["climate"].get("facing_mag_deg"), 133.8)
    check("склонение: проверка MAGNETIC",
          any(c["code"] == "MAGNETIC" for c in data_cl["checks"]), True)
    check("ветер: проверка WIND", any(c["code"] == "WIND" for c in data_cl["checks"]), True)
    check("ветер: гора в данных", data_cl["climate"]["wind"].get("wind_prevailing_mountain"), "申")

    # 11b. 凹风: ветер дует в фасад — гора ветра совпала с горой фасада
    into_face = copy.deepcopy(with_climate)
    into_face["exposure"]["wind_prevailing_mountain"] = into_face["orientation"]["facing_mountain"]
    data_if = L.landform_data(into_face, feixing_fn=feixing)
    check("凹风: предупреждение о ветре в фасад",
          any("凹风" in w for w in data_if["warnings"]), True)

    # 11c. Пакет без климата: поля пусты, но отчёта это не ломает
    no_climate = base_pack()
    data_nc = L.landform_data(no_climate, feixing_fn=feixing)
    check("без климата: пустой блок", data_nc["climate"], {})
    check("без климата: нет проверки WIND",
          any(c["code"] == "WIND" for c in data_nc["checks"]), False)

    # 11d. Старый пакет климата даёт stale_algo
    stale = base_pack()
    stale["algo"]["climate"] = "0.9.0"
    check("stale_algo: климат",
          any("climate" in w for w in L.check_pack_versions(stale)), True)

    # 12. E-019: видимость, водоёмы и «каждый объект один раз»
    split = base_pack()
    split["water"].extend([
        {"id": "osm-Fleet-culvert", "name": "River Fleet", "kind": "culvert", "geom": "line",
         "visible": False, "hidden_share": 0.95, "nearest_m": 404.3, "nearest_mountain": "坤"},
        {"id": "osm-Mixed-canal", "name": "Mixed Canal", "kind": "canal", "geom": "line",
         "visible": True, "hidden_share": 0.5, "nearest_m": 900.0,
         "in_mountain": "子", "out_mountain": "丑", "flow_confidence": "medium"},
        {"id": "osm-Basin-dock", "name": "City Road Basin", "kind": "dock", "geom": "area",
         "visible": True, "hidden_share": 0.0, "nearest_m": 1803.1, "nearest_mountain": "子",
         "area_m2": 10064.8, "site_inside": False},
    ])
    data_split = L.landform_data(split, feixing_fn=feixing)

    water_names = [w["name"] for w in data_split["water"]]
    check("Fleet только в 暗水", "River Fleet" not in water_names, True)
    check("Fleet в 暗水", any("River Fleet" in c["text"] for c in data_split["checks"]
                              if c["code"].startswith("HIDDEN-")), True)
    mixed = next(w for w in data_split["water"] if w["name"] == "Mixed Canal")
    check("смешанный водоток в 來水", mixed["hidden_share"], 0.5)
    check("смешанный: пометка о трубе",
          any("частично в трубе" in c["text"] for c in data_split["checks"]
              if c["code"] == "WATER-Mixed Canal"), True)

    check("водоём не в 來水", "City Road Basin" not in water_names, True)
    check("водоём в разделе водоёмов",
          any(w["name"] == "City Road Basin" for w in data_split["water_bodies"]), True)
    check("водоём: участок на воде или рядом",
          any("рядом, вне контура" in c["text"] for c in data_split["checks"]
              if c["code"] == "WATERBODY-City Road Basin"), True)

    ids = ([w.get("id") for w in data_split["water"]] + [w.get("id") for w in data_split["water_hidden"]]
           + [w.get("id") for w in data_split["water_bodies"]])
    check("каждый объект один раз", len(ids), len(set(ids)))

    # 13. E-021: петля печатается с положением участка и уверенностью
    looped = base_pack()
    looped["water"][0]["loop"] = {"ratio": 3.05, "turn_deg": 183.2, "area_k": 1.16,
                                  "confidence": "low", "margin": {"ratio": 0.017, "turn": 0.018}}
    looped["water"][0]["site_position"] = "outside_concave"
    data_loop = L.landform_data(looped, feixing_fn=feixing)
    loop_text = " ".join(c["text"] for c in data_loop["checks"] if c["code"] == "WATER-River Thames")
    check("петля: положение участка", "внешней стороны вогнутости" in loop_text, True)
    check("петля: уверенность в скобках", "уверенность low" in loop_text, True)
    check("петля low → оговорка",
          any("петля с запасом" in w for w in data_loop["warnings"]), True)

    # 14. R8: пакет до 7.0.0 читается по старой логике, с оговоркой stale_algo
    legacy = json.loads((Path(__file__).resolve().parent.parent
                         / "tests" / "fixtures" / "london-city-site_pack.json").read_text(encoding="utf-8"))
    data_legacy = L.landform_data(legacy, feixing_fn=feixing)
    check("старый пакет: оговорка stale_algo",
          any("stale_algo" in w and "geom" in w for w in data_legacy["warnings"]), True)

    # 15. Свежий лондонский пакет: разделы не пересекаются, Флит в 暗水, бассейн в водоёмах
    fresh = json.loads((Path(__file__).resolve().parent.parent
                        / "tests" / "fixtures" / "london-city-site_pack-7.json").read_text(encoding="utf-8"))
    data_fresh = L.landform_data(fresh, feixing_fn=feixing)
    fresh_water = [w["name"] for w in data_fresh["water"]]
    check("свежий пакет: Темза в 來水", "River Thames" in fresh_water, True)
    check("свежий пакет: Fleet не в 來水", "River Fleet" not in fresh_water, True)
    check("свежий пакет: бассейн в водоёмах",
          any(w["name"].startswith("City Road Basin") for w in data_fresh["water_bodies"]), True)
    fresh_ids = ([w.get("id") for w in data_fresh["water"]]
                 + [w.get("id") for w in data_fresh["water_hidden"]]
                 + [w.get("id") for w in data_fresh["water_bodies"]])
    check("свежий пакет: без повторов", len(fresh_ids), len(set(fresh_ids)))

    # 16. E-020 п.1-2 (доп.): док-каналы, порог площади, причина одинаковых гор
    fresh_codes = [c["code"] for c in data_fresh["checks"]]
    check("док-канал не в 來水", "WATER-West Dock" not in fresh_codes, True)
    check("док-канал не в 來水: Central Basin", "WATER-Central Basin" not in fresh_codes, True)
    check("док-контур в водоёмах", "WATERBODY-West Dock" in fresh_codes, True)
    check("пометка о канале в контуре",
          any("канал внутри контура" in c["text"] for c in data_fresh["checks"]
              if c["code"] == "WATERBODY-West Dock"), True)
    check("мелкий водоём не в отчёте", "WATERBODY-Tower Dock" not in fresh_codes, True)

    same_high = [c["code"] for c in data_fresh["checks"]
                 if c["code"].startswith("WATER-") and c["confidence"] == "high"
                 and L._same_mountains_in_text(c["text"])]
    check("в 來水 нет одинаковых гор с high", same_high, [])
    check("причина печатается в строке",
          any("вход и выход в одной горе: короткий кусок" in c["text"]
              for c in data_fresh["checks"] if c["code"].startswith("WATER-")), True)

    # 17. Вне круга 2 км: только расстояние и сторона, без пары 來水/去水
    far_checks = [c for c in data_fresh["checks"]
                  if c["code"].startswith("WATER-") and "не измерены" in c["text"]]
    check("дальнее русло: пара не печатается", len(far_checks) > 0, True)
    check("дальнее русло: есть сторона",
          all("сторона" in c["text"] and "вход и выход не измерены" in c["text"]
              for c in far_checks), True)
    check("дальнее русло: нет выдуманной пары",
          any("вход —" in c["text"] or "выход —" in c["text"] for c in far_checks), False)

    # 19a. Поверхность реки (берег из отношения, water 8.0.0) — подпись «берег реки»
    river_bank = base_pack()
    river_bank["water"].append({
        "id": "osm-rel28934000-lake", "name": "River Thames", "kind": "lake",
        "nearest_m": 340.0, "nearest_azimuth_deg": 180.0, "nearest_mountain": "午",
        "area_m2": 2429113.7, "site_inside": False, "geom": "area", "visible": True,
        "riverbank_of": "osm-thames-river", "source": "osm_relation",
    })
    bank_data = L.landform_data(river_bank, feixing_fn=feixing)
    bank_text = " ".join(c["text"] for c in bank_data["checks"]
                         if c["code"].startswith("WATERBODY-River Thames"))
    check("берег реки: подпись", "берег реки: River Thames" in bank_text, True)
    check("берег реки: площадь", "2429114" in bank_text, True)

    # 19. Схема site_pack/2: стороны названы back/front/left/right — навык читает оба набора
    schema2 = base_pack()
    old = schema2["four_spirits"]
    schema2["four_spirits"] = {
        "back": old["tortoise"], "front": old["bird"],
        "left": old["dragon"], "right": old["tiger"],
        "left_vs_right": old["dragon_vs_tiger"],
    }
    schema2["schema"] = "site_pack/2"
    data_s2 = L.landform_data(schema2, feixing_fn=feixing)
    codes_old = {c["code"] for c in data["checks"]}
    codes_new = {c["code"] for c in data_s2["checks"]}
    check("схема 2: те же проверки формы", codes_new == codes_old, True)
    check("схема 2: спина выше фасада прочитана",
          any(c["code"] == "SPIRIT-BACK-STRONG" for c in data_s2["checks"]), True)

    # 19a. Море: отдельная строка воды и 明堂 (S2 в vector-geo-site)
    sea_pack = copy.deepcopy(base_pack())
    sea_pack["sea"] = {"present": True, "kind": "bay", "kind_ru": "залив", "nearest_m": 667.0,
                       "sectors": ["巽"], "confidence": "high",
                       "evidence": [{"kind": "polygon", "name": "Port Jackson"}, {"kind": "satellite"}]}
    sea_data = L.landform_data(sea_pack, feixing_fn=feixing)
    sea_check = next((c for c in sea_data["checks"] if c["code"] == "SEA"), None)
    check("море: строка есть", sea_check is not None, True)
    check("море: вид и расстояние", "залив" in sea_check["text"] and "667.0" in sea_check["text"], True)
    check("море: признаки перечислены",
          "polygon" in sea_check["text"] and "satellite" in sea_check["text"], True)
    mingtang = next((c for c in sea_data["checks"] if c["code"] == "MINGTANG"), None)
    check("明堂: море в фасаде распознано",
          mingtang is not None and "перед фасада" in mingtang["text"], True)
    check("море в markdown", "**水 — море.**" in L.landform_markdown(sea_data), True)

    dry = copy.deepcopy(base_pack())
    dry["sea"] = {"present": False, "confidence": "medium", "evidence": []}
    dry_check = next((c for c in L.landform_data(dry, feixing_fn=feixing)["checks"]
                      if c["code"] == "SEA"), None)
    check("море: внутренний город — «не найдено»", "не найдено" in dry_check["text"], True)

    conflict = copy.deepcopy(base_pack())
    conflict["sea"] = {"present": None, "confidence": "low",
                       "note": "OSM моря не видит, а снимок показывает 62.0 % воды",
                       "evidence": [{"kind": "satellite", "share": 0.62}]}
    conflict_data = L.landform_data(conflict, feixing_fn=feixing)
    conflict_check = next(c for c in conflict_data["checks"] if c["code"] == "SEA")
    check("море: конфликт → «не знаю»", "противоречат" in conflict_check["text"], True)
    check("море: конфликт в оговорках",
          any("«не знаю»" in w for w in conflict_data["warnings"]), True)

    # 19. H5–H8: Южное полушарие — две интерпретации, Северное — одна
    def south_pack(**over):
        pack = base_pack()
        pack["site"] = dict(pack["site"], lat=-33.8688, lon=151.2093, utm_epsg=32756)
        # схема 2: стороны названы back/front/left/right (H4)
        pack["schema"] = "site_pack/2"
        pack["four_spirits"] = {"back": {"rel_elev_m": 40.0}, "front": {"rel_elev_m": 5.0},
                                "left": {"rel_elev_m": 12.0}, "right": {"rel_elev_m": 30.0},
                                "left_vs_right": -18.0}
        pack["sun"] = {"source": "NOAA", "days_noon_north": 365, "days_noon_south": 0,
                       "noon_side": {"mountain": "子", "side8": "N"},
                       "noons": [{"event": "december_solstice", "altitude_deg": 79.6,
                                  "azimuth_deg": 0.0, "mountain": "子"}]}
        pack.update(over)
        return pack

    north = L.landform_data(base_pack(), feixing_fn=feixing)
    check("север: одна интерпретация", len(north["interpretations"]), 1)
    check("север: школа classic", north["interpretations"][0]["school"], "classic")
    check("север: расхождений нет", north["divergences"], [])
    check("север: полушарие", north["hemisphere"], "north")

    south = L.landform_data(south_pack(), feixing_fn=feixing)
    check("юг: две интерпретации", len(south["interpretations"]), 2)
    check("юг: первая классика", south["interpretations"][0]["school"], "classic")
    check("юг: вторая зеркало", south["interpretations"][1]["school"], "mirror")
    check("юг: раздел расхождений не пуст", len(south["divergences"]) >= 3, True)
    check("юг: расхождение по стихии севера",
          next(r for r in south["divergences"] if r["topic"] == "Стихия севера")["mirror"],
          "Огонь (火)")

    # 20. --school classic на юге: одна интерпретация и оговорка о второй
    only_classic = L.landform_data(south_pack(), feixing_fn=feixing, school="classic")
    check("юг --school classic: одна", len(only_classic["interpretations"]), 1)
    check("юг --school classic: оговорка о второй",
          any("не построена" in w for w in only_classic["warnings"]), True)
    only_mirror = L.landform_data(south_pack(), feixing_fn=feixing, school="mirror")
    check("юг --school mirror: одна и это зеркало", only_mirror["interpretations"][0]["school"],
          "mirror")

    # 21. Зеркало меняет стихии севера и юга
    classic_view = south["interpretations"][0]
    mirror_view = south["interpretations"][1]
    check("зеркало: север — огонь", mirror_view["elements"]["north"], "Огонь (火)")
    check("зеркало: юг — вода", mirror_view["elements"]["south"], "Вода (水)")
    check("классика: север — вода", classic_view["elements"]["north"], "Вода (水)")

    # 21a. Основание стихий названо по школе: компас — классика, солнце — зеркало.
    # В зеркале «по компасу» описывало бы противоположное правило: север там получает огонь
    # именно потому, что на севере полуденное солнце.
    classic_elements = next(c for c in classic_view["checks"] if c["code"] == "SCHOOL-ELEMENTS")
    mirror_elements = next(c for c in mirror_view["checks"] if c["code"] == "SCHOOL-ELEMENTS")
    check("классика: стихии по компасу",
          classic_elements["text"].startswith("стихии по компасу"), True)
    check("зеркало: стихии по солнцу",
          mirror_elements["text"].startswith("стихии по солнцу"), True)

    # 21b. Отклонение фасада: 15° (гора) — совпадение, до 45° — «близко», дальше — «не совпадает».
    # В base_pack фасад 135°, предпочтительный на юге 180°: 45° — это соседняя гора, не совпадение.
    classic_facing = next(c for c in classic_view["checks"] if c["code"] == "SCHOOL-FACING")
    mirror_facing = next(c for c in mirror_view["checks"] if c["code"] == "SCHOOL-FACING")
    check("фасад 45° от юга — «близко»", "близко" in classic_facing["text"], True)
    check("фасад 45° от юга — не «совпадает»",
          "совпадает" not in classic_facing["text"], True)
    check("фасад 135° от севера — «не совпадает»",
          "не совпадает" in mirror_facing["text"], True)

    # 22. --mirror-dragon: 青龍 и 白虎 меняются местами (по умолчанию включено)
    dragon_on = L.landform_data(south_pack(), feixing_fn=feixing)["interpretations"][1]
    dragon_off = L.landform_data(south_pack(), feixing_fn=feixing,
                                 mirror_dragon=False)["interpretations"][1]
    # в схеме 2 left = 12 м, right = 30 м; зеркало берёт дракона справа
    check("--mirror-dragon: 青龍 справа", dragon_on["dragon"], 30.0)
    check("--mirror-dragon: 白虎 слева", dragon_on["tiger"], 12.0)
    check("без перестановки: 青龍 слева", dragon_off["dragon"], 12.0)
    check("без перестановки: 白虎 справа", dragon_off["tiger"], 30.0)
    check("--mirror-dragon помечен как вариант школы",
          any("вариант школы" in n for n in dragon_on["notes"]), True)

    # 23. --mirror-flying-stars: карта по оси, повёрнутой на 180°
    stars_on = L.landform_data(south_pack(), feixing_fn=feixing)["interpretations"][1]
    stars_off = L.landform_data(south_pack(), feixing_fn=feixing,
                                mirror_flying_stars=False)["interpretations"][1]
    check("--mirror-flying-stars: карта есть", stars_on["chart"] is not None, True)
    check("--mirror-flying-stars: другая карта",
          stars_on["chart"]["facing"] != stars_off["chart"]["facing"], True)
    check("--mirror-flying-stars: ось зеркала = классика + 180",
          (L.MOUNTAIN_CENTER[stars_on["chart"]["facing"]]
           - L.MOUNTAIN_CENTER[stars_off["chart"]["facing"]]) % 360, 180)

    # 24. Экваториальный участок получает строку об экваторе
    eq = south_pack()
    # юг, но близко к экватору: иначе зеркальная школа не применяется вовсе
    eq["site"] = dict(eq["site"], lat=-1.3521, lon=103.8198)
    eq_data = L.landform_data(eq, feixing_fn=feixing)
    check("экватор: флаг", eq_data["equatorial"], True)
    check("экватор: строка в оговорках",
          any("различие школ" in w and "слабее" in w for w in eq_data["warnings"]), True)
    check("экватор: две интерпретации всё равно есть", len(eq_data["interpretations"]), 2)

    # 25. Отчёт юга: общие данные, две интерпретации, расхождения, оговорки; ни одна не «правильная»
    md = L.landform_markdown(south)
    check("отчёт: заголовок юга", md.startswith("# Участок: форма, вода, ориентация (Южное полушарие)"), True)
    check("отчёт: общие данные", "## Общие данные (одинаковы для обеих школ)" in md, True)
    check("отчёт: интерпретация 1", "## Интерпретация 1 — классическая школа" in md, True)
    check("отчёт: интерпретация 2",
          "## Интерпретация 2 — зеркальная школа (Южное полушарие)" in md, True)
    check("отчёт: расхождения", "## Где школы расходятся" in md, True)
    check("отчёт: солнце в общих данных", "日 — солнце и холодный ветер" in md, True)
    check("отчёт: ни одна не названа правильной",
          "не называется правильной" in md, True)
    check("север: отчёт без разделов школ", "## Общие данные" not in L.landform_markdown(north), True)

    # 18. Оговорки: только показанное, остальное одной строкой
    check("оговорки: дальние не перечислены",
          any(w.startswith("ещё ") and "в пакете" in w for w in data_fresh["warnings"]), True)
    low_line = next((w for w in data_fresh["warnings"] if w.startswith("поля с уверенностью low")), "")
    fresh_shown = set(fresh_ids)
    listed = re.findall(r"water\.flow:([^,]+)", low_line)
    check("оговорки: только объекты отчёта",
          [n for n in listed if n not in {str(w.get("name")) for w in data_fresh["water"]}], [])


if __name__ == "__main__":
    run()
    failed = [c for c in CHECKS if not c[1]]
    for name, ok, actual, expected in CHECKS:
        print(("  ok   " if ok else "  FAIL ") + name + (
            "" if ok else ": получено %r, ждали %r" % (actual, expected)))
    print("\n%d/%d проверок пройдено" % (len(CHECKS) - len(failed), len(CHECKS)))
    raise SystemExit(1 if failed else 0)
