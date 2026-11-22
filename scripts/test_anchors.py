#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Регрессионные тесты Vector fengshui-bazi по якорным датам.

Запуск: python3 test_anchors.py  (из каталога scripts/)

Якоря сверены с эталонными репозиториями:
  * 1977-09-23 19:00 → 丁巳 己酉 癸未 壬戌  (china-testing/bazi README)
  * 1990-05-15 12:00 → день 庚辰            (jinchenma94/bazi-skill pai_pan.py)
  * 1893-12-26 12:00 → 癸巳 甲子 丁酉 丙午  (известная карта)
  * 1990-02-03 10:00 → год 己巳 (до 立春)    (bazi-skill якорь)
  * гуа: 1984м=7兑, 1990м=1坎, 2000м=9离, 1990ж=8艮  (八宅 канон)
  * 飞星: 8运子山午向 → 双星到向, центр 4-8-3 (fengshui.skill feixing.md)
"""
from datetime import date

import fengshui_bazi_calc as f

CHECKS = []


def check(name, actual, expected):
    ok = actual == expected
    CHECKS.append((name, ok, actual, expected))
    return ok


def pillars_of(d, hh, mm, tz=8.0, male=True):
    return f.pillars_data(date(*d), hh, mm, tz, False, male)


def hanzi_list(c):
    return [p["hanzi"] for p in c["pillars"]]


# --- бацзы: столпы ---
c = pillars_of((1977, 9, 23), 19, 0, male=False)
check("1977-09-23 19:00 столпы", hanzi_list(c), ["丁巳", "己酉", "癸未", "壬戌"])
check("1977 найнь года", c["pillars"][0]["nayin"], "Земля в песке")

c = pillars_of((1990, 5, 15), 12, 0)
check("1990-05-15 12:00 столпы", hanzi_list(c), ["庚午", "辛巳", "庚辰", "壬午"])

c = pillars_of((1893, 12, 26), 12, 0)
check("1893-12-26 12:00 столпы", hanzi_list(c), ["癸巳", "甲子", "丁酉", "丙午"])
check("1893 大运 обратный (инь-год, мужчина)", c["dayun"]["forward"], False)

c = pillars_of((1990, 2, 3), 10, 0)
check("1990-02-03 год до 立春", c["pillars"][0]["hanzi"], "己巳")
check("1990-02-03 месяц 丑", c["pillars"][1]["hanzi"], "丁丑")

# --- смена дня в 23:00 / 夜子时 ---
c = pillars_of((1990, 5, 15), 23, 30)
check("23:30 день = следующий", c["pillars"][2]["hanzi"], "辛巳")
check("23:30 час", c["pillars"][3]["hanzi"], "戊子")
c2 = f.pillars_data(date(1990, 5, 15), 23, 30, 8.0, True, True)
check("夜子时 день = текущий", c2["pillars"][2]["hanzi"], "庚辰")
check("夜子时 час", c2["pillars"][3]["hanzi"], "丙子")

# --- 八宅: гуа ---
check("гуа 1984 м", f.gua_data(date(1984, 6, 1), "m")["number"], 7)
check("гуа 1990 м", f.gua_data(date(1990, 5, 15), "m")["number"], 1)
check("гуа 2000 м", f.gua_data(date(2000, 6, 1), "m")["number"], 9)
g = f.gua_data(date(1990, 5, 15), "f")
check("гуа 1990 ж", g["number"], 8)
check("гуа 1990 ж: 5 → 艮", g["jigong"], "жен. 5 → 艮(8)")

# --- 玄空飞星: 8运 子山午向 ---
fx = f.feixing_data(180.0, None, 2010, None, 8.0)
check("8运 2010 период", fx["period"], 8)
check("8运 子山午向 формат", fx["format"].split(" ")[0], "双星到向")
check("8运 центр 4-8-3", fx["grid"][5], (4, 8, 3))
check("8运 фасад Ю 8-3-8", fx["grid"][9], (8, 3, 8))

fx2 = f.feixing_data(None, "午", 2018, 2026, 8.0)
check("годовые звёзды 2026 центр", fx2["annual"]["center"], 1)
check("2026 五黄 = Ю", fx2["annual"]["wuhuang"], "Ю")
check("2026 三煞 = С", fx2["annual"]["sansha"], "С (亥子丑)")
check("2026 太岁 = Ю", fx2["annual"]["taisui"], "Ю")

# --- нумерология ---
n = f.numerology_data(date(1990, 5, 15), "Иван Петров", 2026)
check("жизненный путь 1990-05-15", n["life_path"], 3)
check("выражение Иван Петров", n["expression"], 1)
check("психоматрица ячейки", n["psychomatrix"]["cells"],
      {1: 3, 2: 1, 3: 2, 4: 0, 5: 2, 6: 0, 7: 0, 8: 1, 9: 2})
check("рабочие числа", n["psychomatrix"]["working_numbers"], [30, 3, 28, 10])

# --- зодиак ---
z = f.zodiac_verdict(0, 1)   # Крыса + Бык
check("Крыса+Бык = 六合", z["rel"], "六合")
check("Крыса+Бык балл", z["score"], 95)
z = f.zodiac_verdict(0, 6)   # Крыса + Лошадь
check("Крыса+Лошадь = 六冲", z["rel"], "六冲")
z = f.zodiac_verdict(0, 8)   # Крыса + Обезьяна
check("Крыса+Обезьяна = 三合", z["rel"], "三合")

# --- совместимость (smoke) ---
c1 = pillars_of((1990, 5, 15), 8, 30)
c2 = pillars_of((1992, 3, 8), 14, 0, male=False)
m = f.match_data(c1, c2)
check("балл в диапазоне", 0 <= m["score"] <= 100, True)
check("категория по баллу", m["band"],
      next(label for th, label in f.BANDS if m["score"] >= th))


def main():
    failed = [c for c in CHECKS if not c[1]]
    for name, ok, actual, expected in CHECKS:
        print("%s %s" % ("PASS" if ok else "FAIL", name))
        if not ok:
            print("      ожидалось: %r" % (expected,))
            print("      получено:  %r" % (actual,))
    print("\n%d/%d проверок пройдено" % (len(CHECKS) - len(failed), len(CHECKS)))
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
