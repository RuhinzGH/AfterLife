"""The plain-language explanation (S2-08): a language model words the result,
and is checked so it can only repeat numbers the page already shows.

How it stays honest:
  1. facts() picks a small set of already-computed results from /api/assess
     (score, its adjustments, years, support date, usage fit, repair outlook,
     carbon). Nothing about the person or the device's identity is sent.
  2. The model is told to use only those facts and to add no number of its own.
  3. check_numbers() then reads every number in its reply. If any is not in the
     facts (allowing only the rounding of a fact, e.g. 21.1 -> 21), the reply is
     thrown away and the rule-based summary is used instead, with the reason.

So the model can make the result easier to read, but it cannot change, invent or
mis-copy a figure without the reply being rejected.
"""
from __future__ import annotations

import json
import re
from typing import Any

from . import llm

SYSTEM = (
    "You explain a laptop or phone assessment to its owner, who is not technical. "
    "Use ONLY the facts in the JSON you are given. Never add a number, date, price, "
    "percentage or fact that is not in it, and never change one. Do not give advice that "
    "is not in the facts. Write 4 to 6 short sentences of plain English, addressed to "
    "'you', with no lists, no markdown, no exclamation marks and no jargon. Cover: what "
    "the score is and the main things that moved it; roughly how long the device should "
    "stay useful; the most useful fix if one is given (if none is given, say nothing needs "
    "fixing now); and whether replacing it would be greener. Never suggest buying a new "
    "device: the recommended option is 'best_option'. If something was not measured, say so "
    "plainly."
)

#: What each score adjustment means, in words the model cannot misread
#: ("ML end-of-life risk" was read as the machine's machine-learning features).
MEANING = {
    "ML end-of-life risk": "estimated chance that devices like this one end up beyond repair, "
                           "from a model trained on community repair records",
    "Security support horizon": "how soon this operating system stops getting security updates",
    "battery wear": "the battery holds less of its original charge",
    "age": "the machine is older than six years",
    "reported fault": "the owner reported a fault",
}

_NUM = re.compile(r"(?<![\w.])\d[\d,]*(?:\.\d+)?")


def _numbers(text: str) -> set[str]:
    out = set()
    for m in _NUM.findall(text):
        n = m.replace(",", "")
        try:
            v = float(n)
        except ValueError:
            continue
        out.add(f"{v:g}")
    return out


_MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august",
           "september", "october", "november", "december"]
_ISO = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_M = "(" + "|".join(_MONTHS) + ")"
_WRITTEN_DATES = [
    re.compile(r"\b(\d{1,2})\s+" + _M + r",?\s+(\d{4})\b", re.I),    # 12 October 2027
    re.compile(r"\b" + _M + r"\s+(\d{1,2}),?\s+(\d{4})\b", re.I),    # October 12, 2027
    re.compile(r"\b" + _M + r",?\s+(\d{4})\b", re.I),                 # October 2027
]


def _fact_dates(facts_text: str) -> set[tuple[int, int]]:
    return {(int(y), int(m)) for y, m, _ in _ISO.findall(facts_text)}


def _allowed(facts: dict[str, Any]) -> set[str]:
    """Every number in the facts, plus each one rounded to a whole number. Dates
    are left out: their parts (a day of 12) must not license "12 years"; dates
    are checked as dates instead."""
    text = _ISO.sub(" ", json.dumps(facts, ensure_ascii=False))
    base = _numbers(text)
    rounded = {f"{round(float(n)):g}" for n in base}
    return base | rounded


def _strip_dates(text: str, dates: set[tuple[int, int]]) -> tuple[str, list[str]]:
    """Remove dates that match a fact (same year and month); report others."""
    bad = []

    def keep_or_flag(m: re.Match) -> str:
        parts = m.groups()
        month = next(_MONTHS.index(p.lower()) + 1 for p in parts if p and p.lower() in _MONTHS)
        year = int(parts[-1])
        if (year, month) in dates:
            return " "
        bad.append(m.group(0))
        return " "

    for pat in _WRITTEN_DATES:
        text = pat.sub(keep_or_flag, text)
    text = _ISO.sub(lambda m: " " if (int(m.group(1)), int(m.group(2))) in dates
                    else (bad.append(m.group(0)) or " "), text)
    return text, bad


def check_numbers(text: str, facts: dict[str, Any]) -> list[str]:
    """Numbers (and dates) in the reply that are not in the facts. Empty means it passed."""
    rest, bad_dates = _strip_dates(text, _fact_dates(json.dumps(facts, ensure_ascii=False)))
    allowed = _allowed(facts)
    return sorted(bad_dates + [n for n in _numbers(rest) if n not in allowed])


def facts(a: dict[str, Any], tier: str | None = None) -> dict[str, Any]:
    """The computed results the model may talk about, and nothing else."""
    blend, pipe = a.get("blend") or {}, a.get("pipeline") or {}
    f: dict[str, Any] = {
        "scan": "deep scan (measured hardware)" if tier == "full scan" else "instant browser scan (hardware not measured)",
        "score": blend.get("combined_score"),
        "score_scale_max": 100,
        "grade": blend.get("grade"),
        "starting_hardware_score": blend.get("hardware_trust"),
        "score_adjustments": [{"what": MEANING.get(x.get("factor"), x.get("factor")),
                               "detail": x.get("detail"), "points": x.get("delta")}
                              for x in blend.get("adjustments", [])],
        "estimated_years_of_safe_use_left": pipe.get("estimated_remaining_years"),
        "strengths": (a.get("key_points") or {}).get("strengths", []),
        "weaknesses": (a.get("key_points") or {}).get("weaknesses", []),
    }
    sh = a.get("support_horizon")
    if sh:
        f["security_updates"] = {"ordinary_updates_end": sh.get("eol_from"), "ordinary_updates_ended": sh.get("is_eol")}
    cliff = a.get("support_cliff")
    if cliff:
        f.setdefault("security_updates", {})["extended_updates_until"] = cliff.get("date")
    fit = a.get("usage_fit")
    if fit:
        f["usage_fit"] = {"use": fit.get("label"), "verdict": fit.get("verdict"), "outlook": fit.get("timeline")}
    cond = ((a.get("uplift") or {}).get("condition")) or {}
    if cond.get("actions"):
        f["best_fix"] = {"actions": [x.get("action") for x in cond["actions"]],
                         "score_after": cond.get("projected_score"), "grade_after": cond.get("projected_grade")}
    ev = a.get("repair_evidence")
    if ev:
        f["repair_records"] = [{"fault": t.get("label"), "percent_repaired": round(t.get("fixed_pct", 0))}
                               for t in ev.get("themes", [])]
    ct = a.get("carbon_tradeoff")
    if ct:
        f["carbon"] = ct.get("headline")
    paths = a.get("pathways") or []
    if paths:
        f["best_option"] = paths[0].get("label")
    return f


def explain(assessment: dict[str, Any], tier: str | None = None) -> dict[str, Any]:
    """{"text", "source", "checked"}; falls back to the rule-based summary."""
    rule = ((assessment.get("narrative") or {}).get("summary")) or ""
    if not llm.available():
        return {"text": rule, "source": "rule-based", "checked": True, "reason": "no language model configured"}
    f = facts(assessment, tier)
    try:
        text = llm.chat(SYSTEM, "Facts:\n" + json.dumps(f, ensure_ascii=False, indent=1))
    except Exception as exc:  # noqa: BLE001 -- any failure means the rule-based text stays
        return {"text": rule, "source": "rule-based", "checked": True,
                "reason": f"language model unavailable ({llm.describe_error(exc)})"}
    text = " ".join(text.split())
    bad = check_numbers(text, f)
    if bad:
        return {"text": rule, "source": "rule-based", "checked": True,
                "reason": f"the model's wording used numbers not on the page ({', '.join(bad[:5])}), so it was discarded"}
    return {"text": text, "source": f"language model ({llm.model()})", "checked": True}
