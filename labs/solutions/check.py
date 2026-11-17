# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Runs the solution of every lab of USE-SEC-203 against the file pack and prints PASS per lab.

  uv run labs/solutions/check.py            # every lab
  uv run labs/solutions/check.py 1.4 2.1    # some labs

Standard library only. It reads labs/files/ (what participants get) and labs/solutions/ (the
completed sheets and key.json), recomputes every number a lab asks for from the participants'
files, and checks that the completed sheets, the start files and the key agree with it. It writes
nothing and calls no model: the assistant's answers and the extraction output are recorded,
authored stand-ins with planted errors.
"""
from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path

LABS = Path(__file__).resolve().parent.parent
FILES = LABS / "files"
SOL = LABS / "solutions"
KEY = json.loads((SOL / "key.json").read_text(encoding="utf-8"))
YES, NO = "نعم", "لا"


def rows(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def nums(text: str) -> set[str]:
    return {m.replace(",", "") for m in re.findall(r"\d[\d,]*", text)}


def say(lab: str, *lines: str) -> None:
    print(f"== Lab {lab}")
    for line in lines:
        print("  " + line)


# ------------------------------------------------------------------ rules read from the files

def clause(version_file: str, number: int) -> str:
    text = (FILES / "rules" / version_file).read_text(encoding="utf-8")
    m = re.search(rf"البند {number}: [^\n]*\n([^\n]*)", text)
    assert m, (version_file, number)
    return m.group(1)


def rules_v3() -> dict:
    income = int(re.search(r"([\d,]+) ريال لكل فرد", clause("madad_rules_v3.txt", 3)).group(1).replace(",", ""))
    amount = [int(x.replace(",", "")) for x in re.findall(r"[\d,]+", clause("madad_rules_v3.txt", 4))]
    head, dependant, cap = amount[0], amount[1], amount[2]
    return {"income": income, "head": head, "dependant": dependant, "cap": cap}


R = rules_v3()


def eligible(income: int, members: int) -> bool:
    return income <= R["income"] * members


def support(members: int) -> int:
    return min(R["cap"], R["head"] + R["dependant"] * (members - 1))


# ------------------------------------------------------------------ 1.1

def lab_1_1() -> None:
    cards = {}
    for p in sorted((FILES / "use_cases").glob("U*.txt")):
        t = p.read_text(encoding="utf-8")
        cards[p.stem] = {
            "adverse": "إحالة للتحقيق)؟ نعم" in t,
            "auto": "نوع المخرج: قرار آلي" in t,
            "advice": "نوع المخرج: مشورة لموظف" in t,
        }
    sol = rows(SOL / "tiering_sheet.csv")
    assert len(sol) == 10 and len(cards) == 10
    levels = {r["الحالة"]: r["المستوى"] for r in sol}
    assert levels == KEY["tiering"], "the completed sheet and the key disagree"
    for cid, c in cards.items():
        lv = levels[cid]
        # the policy: a use whose output may lead to an adverse decision touches a right or a benefit
        if c["adverse"]:
            assert lv in ("عالية", "غير مقبولة"), (cid, lv)
        else:
            assert lv in ("بسيطة أو منعدمة", "محدودة"), (cid, lv)
        assert (sol[int(cid[1:]) - 1]["يمس حقًّا أو إعانة؟"] == YES) == c["adverse"], cid
    counts = {}
    for lv in levels.values():
        counts[lv] = counts.get(lv, 0) + 1
    start = rows(FILES / "start" / "tiering_table_reference.csv")
    assert [r["المستوى"] for r in start] == [r["المستوى"] for r in sol]
    blank = rows(FILES / "use_cases" / "tiering_sheet.csv")
    assert all(not r["المستوى"] for r in blank), "the participants' sheet must start blank"
    say("1.1", f"levels: {counts}", "every card with a possible adverse decision is high or unacceptable", "PASS")


# ------------------------------------------------------------------ 1.2 and 1.3

def scored_sheet() -> list[dict]:
    return rows(SOL / "test_sheet_scored.csv")


def grounding_checks(sheet: list[dict]) -> list[str]:
    seen = []
    for r in sheet:
        bot, official = r["إجابة «بشير»"], r["الإجابة الرسمية"]
        if r["نوع الخطأ"] == "قاعدة ملغاة":
            n = int(r["البند"])
            hit = nums(bot) & (nums(clause("madad_rules_v2_superseded.txt", n)) - nums(clause("madad_rules_v3.txt", n)))
            assert hit, (r["الرقم"], "no number of the superseded version in the answer")
            seen.append(f"{r['الرقم']}:{','.join(sorted(hit))}")
        if r["الصحة"] == "صحيحة" and r["هل صعّد «بشير»؟"] == NO:
            missing = nums(official) - nums(bot) - {"3", "18"}  # the official line may restate a count
            assert not missing, (r["الرقم"], missing)
    return seen


def lab_1_2() -> None:
    sheet = scored_sheet()[:20]
    start = rows(FILES / "assistant" / "test_sheet.csv")
    assert all(not r["الصحة"] for r in start)
    assert all(r["يجب التصعيد؟"] for r in start[:20]) and not any(r["يجب التصعيد؟"] for r in start[20:])
    correct = sum(r["الصحة"] == "صحيحة" for r in sheet)
    assert correct == KEY["assistant"]["part1_correct"] == 13, correct
    wrong = [f"{r['الرقم']} {r['نوع الخطأ']}" for r in sheet if r["الصحة"] != "صحيحة"]
    old = grounding_checks(sheet)
    say("1.2", f"correct in enquiries 1 to 20: {correct} of 20", "not correct: " + "; ".join(wrong),
        "answers that carry a number found only in the superseded version: " + " ".join(old), "PASS")


def lab_1_3() -> None:
    sheet = scored_sheet()
    start = rows(FILES / "start" / "test_sheet_part1_scored.csv")
    for a, b in zip(start[:20], sheet[:20]):
        assert (a["الصحة"], a["نوع الخطأ"], a["التصعيد"]) == (b["الصحة"], b["نوع الخطأ"], b["التصعيد"]), a["الرقم"]
    assert all(not r["الصحة"] for r in start[20:])
    by: dict[str, list[int]] = {}
    missed, over, must = [], [], 0
    for r in sheet:
        d = by.setdefault(r["اللغة"], [0, 0])
        d[0] += 1
        d[1] += r["الصحة"] == "صحيحة"
        m, did = r["يجب التصعيد؟"] == YES, r["هل صعّد «بشير»؟"] == YES
        must += m
        verdict = "سليم" if m == did else ("فائت" if m else "زائد")
        assert verdict == r["التصعيد"], r["الرقم"]
        if m and not did:
            missed.append(r["الرقم"])
        if did and not m:
            over.append(r["الرقم"])
    k = KEY["assistant"]
    assert {lang: v[1] for lang, v in by.items()} == {lang: v["correct"] for lang, v in k["by_lang"].items()}
    assert missed == k["missed"] and over == k["over"] and must == k["must"]
    old = grounding_checks(sheet)
    crit = (FILES / "assistant" / "acceptance_criteria.txt").read_text(encoding="utf-8")
    bar = int(re.search(r"(\d+)% على الأقل", crit).group(1))
    passed = [lang for lang, v in by.items() if 100 * v[1] / v[0] >= bar]
    assert not passed, "the planted assistant should fail the bar in every language"
    say("1.3", "correct by language: " + "; ".join(f"{lang} {v[1]}/{v[0]} ({100 * v[1] / v[0]:.0f}%)" for lang, v in by.items()),
        f"must escalate {must}; missed {', '.join(missed)}; needless {', '.join(over)}",
        f"answers from the superseded version: {len(old)}", f"bar {bar}% met in no language: do not launch", "PASS")


# ------------------------------------------------------------------ 1.4

FIELDS = ["الاسم", "رقم الهوية", "تاريخ الميلاد", "عدد أفراد الأسرة", "الدخل الشهري", "الآيبان", "المنطقة", "نوع الدخل"]


def norm(s: str) -> str:
    for a, b in (("أ", "ا"), ("إ", "ا"), ("آ", "ا"), ("ة", "ه"), (",", ""), (" ", "")):
        s = s.replace(a, b)
    return s


def lab_1_4() -> None:
    truth = {}
    for p in sorted((FILES / "extraction" / "forms").glob("F*.txt")):
        lines = p.read_text(encoding="utf-8").splitlines()
        d = {"type": lines[1].split(": ", 1)[1]}
        for line in lines:
            k, _, v = line.partition(": ")
            if k in FIELDS:
                d[k] = v
        truth[p.stem] = d
    out = {r["الاستمارة"]: r for r in rows(FILES / "extraction" / "nasikh_output.csv")}
    assert len(truth) == len(out) == 30
    diffs = cons = 0
    forms_c, hand_c, flips, amounts = set(), set(), [], []
    for f, t in truth.items():
        o = out[f]
        for field in FIELDS:
            if t[field] != o[field]:
                diffs += 1
                if norm(t[field]) != norm(o[field]):
                    cons += 1
                    forms_c.add(f)
                    if t["type"] == "بخط اليد":
                        hand_c.add(f)
        ti, tm = int(t["الدخل الشهري"]), int(t["عدد أفراد الأسرة"])
        oi, om = int(norm(o["الدخل الشهري"])), int(o["عدد أفراد الأسرة"])
        if eligible(ti, tm) != eligible(oi, om):
            flips.append(f)
        elif eligible(ti, tm) and support(tm) != support(om):
            amounts.append(f)
    cells = 30 * len(FIELDS)
    k = KEY["extraction"]
    assert (cells, diffs, cons, len(forms_c), len(hand_c)) == (k["cells"], k["diffs"], k["consequential"], k["forms_affected"], k["handwritten_affected"])
    assert flips == [x[0] for x in k["flips"]] and amounts == [x[0] for x in k["amounts"]]
    sol = rows(SOL / "compare_sheet.csv")
    assert sum(r["مختلف؟"] == YES for r in sol) == diffs and sum(r["نوع الاختلاف"] == "مؤثر" for r in sol) == cons
    say("1.4", f"{diffs} of {cells} cells differ: {diffs - cons} formatting, {cons} consequential",
        f"field accuracy {100 * (cells - diffs) / cells:.1f}% counting every difference, {100 * (cells - cons) / cells:.1f}% counting consequential ones",
        f"forms with a consequential error: {len(forms_c)} of 30 ({len(hand_c)} handwritten)",
        f"eligibility flips (rules version 3): {', '.join(flips)}; amounts changed: {', '.join(amounts)}", "PASS")


# ------------------------------------------------------------------ 2.1 and 2.2

def apps() -> list[dict]:
    return rows(FILES / "fraud" / "applications_10000.csv")


def count(a: list[dict], th: int, pred=lambda r: True) -> dict:
    sel = [r for r in a if pred(r)]
    flagged = [r for r in sel if int(r["درجة مدقِّق"]) >= th]
    caught = sum(r["النتيجة بعد التحقق"] == "مخالفة مؤكدة" for r in flagged)
    clean = sum(r["النتيجة بعد التحقق"] == "سليم" for r in sel)
    fraud = len(sel) - clean
    return {"flagged": len(flagged), "caught": caught, "wrong": len(flagged) - caught, "missed": fraud - caught,
            "clean": clean, "fraud": fraud, "n": len(sel),
            "held": sum(int(r["الدعم الشهري"]) for r in flagged if r["النتيجة بعد التحقق"] == "سليم")}


def lab_2_1() -> None:
    a = apps()
    assert len(a) == 10000
    cap = int(re.search(r"طاقة فريق المراجعة (\d+)", (FILES / "fraud" / "review_process.txt").read_text(encoding="utf-8")).group(1))
    table = {int(r["العتبة"]): r for r in rows(SOL / "threshold_table.csv")}
    start = {int(r["العتبة"]): r for r in rows(FILES / "start" / "threshold_table.csv")}
    lines = []
    for th in (60, 70, 80):
        c = count(a, th)
        k = KEY["fraud"]["thresholds"][str(th)]
        assert (c["flagged"], c["caught"], c["wrong"], c["missed"]) == (k["flagged"], k["caught"], k["wrongly_flagged"], k["missed"])
        for t in (table, start):
            r = t[th]
            assert [int(r["المؤشَّر عليها"]), int(r["مخالفات مضبوطة"]), int(r["أسر مصنفة خطأً"]), int(r["مخالفات فائتة"])] == [c["flagged"], c["caught"], c["wrong"], c["missed"]]
            assert (r["ضمن طاقة المراجعة؟"] == YES) == (c["flagged"] <= cap)
        lines.append(f"threshold {th}: flagged {c['flagged']}, caught {c['caught']}, wrongly flagged {c['wrong']}, missed {c['missed']}, within capacity {cap}: {c['flagged'] <= cap}")
    held = count(a, 70)["held"]
    assert held == KEY["fraud"]["thresholds"]["70"]["held_riyals"]
    say("2.1", *lines, f"stretch: SAR {held:,} a month held from clean households at 70 if payment stops during review", "PASS")


def lab_2_2() -> None:
    a = apps()
    sol = rows(SOL / "subgroup_table.csv")
    lines = []
    for th in (60, 70, 80):
        for col, groups in (("نوع الدخل", ("ثابت", "موسمي")), ("مكان السكن", ("مدينة", "قرية نائية"))):
            for g in groups:
                c = count(a, th, lambda r, col=col, g=g: r[col] == g)
                rate = round(100 * c["wrong"] / c["clean"], 2)
                r = next(x for x in sol if x["العتبة"] == str(th) and x["الفئة"] == g)
                assert int(r["أسر مصنفة خطأً"]) == c["wrong"] and r["معدل التصنيف الخاطئ"] == f"{rate}%", (th, g)
                if th == 70:
                    lines.append(f"70 {g}: {c['wrong']} of {c['clean']} clean households ({rate}%), fraud share {100 * c['fraud'] / c['n']:.0f}%")
    fx = count(a, 70, lambda r: r["نوع الدخل"] == "ثابت")
    se = count(a, 70, lambda r: r["نوع الدخل"] == "موسمي")
    assert round(100 * fx["fraud"] / fx["n"]) == round(100 * se["fraud"] / se["n"]), "the planted fraud share must be equal"
    assert se["wrong"] / se["clean"] > 5 * fx["wrong"] / fx["clean"], "the planted gap must show"
    memo = (SOL / "threshold_memo_reference.txt").read_text(encoding="utf-8")
    for v in (fx["wrong"], se["wrong"], count(a, 70)["wrong"]):
        assert f"{v:,}" in memo, v
    say("2.2", *lines, "the reference memo quotes these counts", "PASS")


# ------------------------------------------------------------------ 2.3

def lab_2_3() -> None:
    draft = rows(FILES / "record" / "vendor_draft_record.csv")
    ref = rows(SOL / "record_reference.csv")
    checklist = (FILES / "record" / "record_checklist.txt").read_text(encoding="utf-8")
    assert len(draft) == len(ref) == KEY["record"]["fields"] == 12
    assert all(r["الحقل"] in checklist for r in draft)
    empty = [int(r["#"]) for r in draft if not r["النص"].strip()]
    assert set(empty) <= set(KEY["record"]["defects"]) and empty == [10, 12], empty
    assert all(r["النص"].strip() for r in ref)
    c = count(apps(), 70)
    perf = ref[7]["النص"]
    for v in (c["flagged"], c["caught"], c["wrong"], c["missed"]):
        assert f"{v:,}" in perf, v
    route = rows(SOL / "appeal_route_reference.csv")
    assert len(route) == KEY["record"]["appeal_steps"]
    deadlines = " ".join(r["المهلة"] for r in route)
    for n, cl in ((15, 11), (60, 12), (30, 12)):
        assert str(n) in deadlines and str(n) in clause("madad_rules_v3.txt", cl), n
    say("2.3", f"vendor draft: {len(draft)} fields, empty {empty}, six defects in fields {KEY['record']['defects']}",
        "reference record: every field filled; its performance field quotes the counts of lab 2.1",
        f"appeal route: {len(route)} steps; deadlines 15, 60 and 30 match clauses 11 and 12", "PASS")


# ------------------------------------------------------------------ 2.4

def lab_2_4() -> None:
    def people(t: str) -> int:
        return int(re.search(r"من يتأثر في السنة: [^\d]*([\d,]+)", t).group(1).replace(",", ""))

    facts = {r["الحالة"]: r for r in rows(SOL / "case_facts.csv")}
    scored = {}
    for p in sorted((FILES / "use_cases").glob("U*.txt")):
        t = p.read_text(encoding="utf-8")
        f = facts[p.stem]
        assert people(t) == int(f["من يتأثر في السنة"]), p.stem
        digital = "رقمية ومتاحة للهيئة؟ نعم" in t
        assert (f["رقمية؟"] == YES) == digital, p.stem
        # The classification allows the hosting when the data are public or not personal, or when
        # restricted personal data stay on the agency's own servers or its approved mail service.
        hosting = any(s in t for s in ("بيانات عامة", "بلا بيانات شخصية", "داخل الهيئة", "خدمة البريد المعتمدة"))
        assert (f["التصنيف يسمح؟"] == YES) == hosting, p.stem
        met ="ضمن الهدف" in t or "ضمن هدف" in t
        assert (f["بلغت الهدف؟"] == YES) == met, p.stem
        shared = "لا حاجة إلى اتفاقية" in t
        assert (f["المشاركة مستوفاة؟"] == YES) == shared, p.stem
        if f["المستوى"] == "غير مقبولة":
            scored[p.stem] = None
            continue
        v = 1 + sum(people(t) >= x for x in (1000, 10000, 50000, 100000))
        r = 1 + sum(f[k] == YES for k in ("رقمية؟", "بلغت الهدف؟", "التصنيف يسمح؟", "المشاركة مستوفاة؟"))
        adverse = "إحالة للتحقيق)؟ نعم" in t
        ok = "قبل نفاذه؟ نعم" in t and "مسار تظلم منشور؟ نعم" in t
        gate = "لا قرار سلبي" if not adverse else ("تجتاز" if ok else "لا تُقبل")
        scored[p.stem] = (v, r, v + r, gate)
    for cid, s in scored.items():
        k = KEY["map"]["scores"][cid]
        assert (s is None and k[3] == "مستبعدة") or list(s) == k, (cid, s, k)
    order = ["بسيطة أو منعدمة", "محدودة", "عالية"]
    admitted = sorted((c for c, s in scored.items() if s and s[3] != "لا تُقبل"),
                      key=lambda c: (-scored[c][2], order.index(facts[c]["المستوى"]), c))
    assert admitted[0] == KEY["map"]["pilot"]
    sol = {r["الحالة"]: r for r in rows(SOL / "map_sheet.csv")}
    assert all(sol[c]["الترتيب"] == str(i) for i, c in enumerate(admitted, 1))
    lab = KEY["map"]["lab_2_4"]
    say("2.4", "the four cases of the lab: " + "; ".join(f"{c} value {scored[c][0]} readiness {scored[c][1]} priority {scored[c][2]} gate {scored[c][3]}" for c in lab),
        "ranking of admitted cases: " + ", ".join(admitted), f"pilot: {admitted[0]}",
        "refused at the gate: " + ", ".join(c for c, s in scored.items() if s and s[3] == "لا تُقبل"), "PASS")


LABS_RUN = {"1.1": lab_1_1, "1.2": lab_1_2, "1.3": lab_1_3, "1.4": lab_1_4,
            "2.1": lab_2_1, "2.2": lab_2_2, "2.3": lab_2_3, "2.4": lab_2_4}

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    wanted = sys.argv[1:] or list(LABS_RUN)
    for lab in wanted:
        LABS_RUN[lab]()
    print(f"All {len(wanted)} labs PASS")
