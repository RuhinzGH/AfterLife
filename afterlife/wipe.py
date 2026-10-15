"""Verify that a device looks factory-fresh after a guided Windows reset.

Scope, stated once and repeated in the UI: this is **not** forensic erasure
verification. Tools like Blancco overwrite sectors and certify the result; that
is a different, harder, genuinely destructive piece of software and building a
half version of it would be worse than not building one. What this does is check
that the obvious traces of a previous owner are gone -- no leftover user
profiles, no files in the personal folders, no saved networks, no installed
software, and an operating system that was installed recently enough to be
consistent with the reset having actually happened.

The honest failure mode is disclosed rather than hidden: someone who deletes
their files by hand without resetting could pass these checks. That is why the
passport records *"looks factory-fresh"*, with the date and the exact evidence,
rather than *"securely erased"*.

`check()` never raises and never guesses. A collector that could not read the
directories at all yields `unknown`, which the UI renders as "we couldn't
check", never as a pass.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Any

#: A freshly reset machine has exactly one profile (the account created during
#: out-of-box setup). Two or more means a previous owner's profile survived.
MAX_CLEAN_PROFILES = 1

#: Windows itself leaves a handful of items in a new profile's folders, and the
#: collector already filters desktop.ini. A small allowance absorbs the rest
#: (a stray shortcut, an OEM welcome PDF) without waving through a real library
#: of documents.
MAX_CLEAN_FILES = 12

#: A reset clears saved networks, but the machine has to rejoin one to reach this
#: app at all -- so exactly one is the expected clean result, not zero.
MAX_CLEAN_WIFI = 2

#: Windows ships with a set of classic installed entries (redistributables,
#: driver packages) even on a clean image. Measured on freshly imaged machines
#: this sits well under 30; a used machine runs to several times that.
MAX_CLEAN_APPS = 30

#: If Windows was installed years ago, no reset happened -- "Reset this PC"
#: rewrites the install date. This is the check that makes hand-deleting files
#: insufficient to fake a pass.
MAX_CLEAN_INSTALL_DAYS = 30


@dataclass
class WipeCheck:
    status: str                       # clean | not_clean | unknown
    checks: list[dict[str, Any]] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)
    verified_at: str | None = None
    note: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status, "checks": self.checks, "failures": self.failures,
            "verified_at": self.verified_at, "note": self.note,
        }


def _check(label: str, ok: bool | None, detail: str) -> dict[str, Any]:
    return {"label": label, "ok": ok, "detail": detail}


SYSTEM = (
    "You are Afterlife's wipe-check explainer. A computer has been checked for "
    "whether it looks factory-fresh after a Windows reset. The verdict is already "
    "decided; you are only putting it into plain words for someone about to sell or "
    "buy the machine, who is not technical. "
    "Reply with ONLY a JSON object, no prose outside it, no markdown fences. "
    "Rules you must not break:\n"
    "1. A check listed as PASSED is not a problem. A freshly reset PC still has "
    "exactly one user account, a couple of Windows' own files, the Wi-Fi network it "
    "is using right now, and the programs Windows ships with. Those numbers are what "
    "a clean machine looks like -- never describe a passed check as something still "
    "to be removed, and never contradict or hedge the verdict you were given.\n"
    "2. Never claim data is securely erased, unrecoverable or destroyed. This checks "
    "what is visible, nothing more, and saying otherwise would be a dangerous "
    "promise.\n"
    "3. Never invent a check, and never state a number that is not in the input.\n"
    "If the verdict is clean, say so plainly and note the one caveat: it means no "
    "visible traces are left, not that deleted data is gone forever. If it is not "
    "clean, say which checks failed and what to do. "
    "Tone: dry, plain, unfussy. No exclamation points, no emoji, no reassurance "
    "padding."
)


def narrate(result: dict[str, Any]) -> dict[str, Any]:
    """One short plain-English reading of the wipe result.

    Same contract as every other narrated card here: the verdict and every number
    are decided in code above, and the model only puts them into a sentence. It is
    also guarded afterwards -- see _overclaims() -- because this is the one card
    where a model reaching for a stronger word than the evidence supports would be
    an actual liability rather than a style problem.
    """
    from .llm import _parse_json, available, chat, describe_error

    fallback = {"text": result.get("note", ""), "source": "fallback"}
    if not available():
        return fallback

    status = result["status"]
    checks = result.get("checks", [])
    # Passed and failed are presented as two separate labelled lists rather than one
    # list with an ok flag. Given the flag, the model reliably read every detail
    # string as a complaint and wrote "the check passed, but three files remain" --
    # inverting a verdict that was already decided. Splitting them removes the
    # ambiguity at the source instead of arguing with it in the prompt.
    passed = [f"{c['label']} ({c['detail']})" for c in checks if c["ok"] is True]
    failed = [f"{c['label']} ({c['detail']})" for c in checks if c["ok"] is False]
    verdict = {
        "clean": "CLEAN -- every check passed, the machine looks factory-fresh",
        "not_clean": "NOT CLEAN -- the machine still shows traces of its owner",
        "unknown": "UNKNOWN -- some checks could not be read, so nothing is confirmed",
    }[status]

    prompt = (
        "Write 2-3 sentences explaining this result, as JSON with a single key "
        "\"text\". Use only what is below.\n\n"
        f"VERDICT: {verdict}\n"
        f"CHECKS THAT PASSED (these are fine, not problems): {passed or 'none'}\n"
        f"CHECKS THAT FAILED (these are the problems, if any): {failed or 'none'}\n"
    )
    try:
        raw, source = chat(SYSTEM, prompt, temperature=0.4, max_tokens=400)
        text = (_parse_json(raw).get("text") or "").strip()
        if not text:
            return fallback
        if _overclaims(text):
            return {"text": result.get("note", ""), "source": f"{source} (rejected: overclaimed erasure)"}
        if _contradicts(text, status):
            return {"text": result.get("note", ""), "source": f"{source} (rejected: contradicted verdict)"}
        return {"text": text, "source": source}
    except Exception as exc:  # noqa: BLE001
        return {"text": result.get("note", ""), "source": f"fallback ({describe_error(exc)})"}


#: Phrases that would turn a visible-traces check into a data-destruction promise.
#: The prompt forbids these; this is what makes the prohibition real. Same lesson as
#: the replace-the-machine guard in hardening.py -- an instruction to a model is not
#: a control, checking the output is.
_OVERCLAIM_PHRASES = (
    "securely erased", "securely wiped", "permanently deleted", "unrecoverable",
    "cannot be recovered", "can't be recovered", "irrecoverable", "destroyed",
    "shredded", "military-grade", "guaranteed",
)


#: Words that flip an overclaim into exactly the disclaimer we want. "Deleted data
#: is unrecoverable" is the promise to block; "not a guarantee that deleted data is
#: unrecoverable" is the sentence this module exists to make. A plain substring
#: match cannot tell those apart -- it rejected correct output, and rejected the
#: fallback it fell back to, since that disclaimer is written in the same shape.
_NEGATORS = ("not ", "n't", "never", "no guarantee", "cannot", "can not",
             "rather than", "instead of", "does not", "doesn't", "isn't")

#: How far back to look for a negator. Long enough to span "this is not a forensic
#: guarantee that deleted data is", short enough not to reach into a previous
#: sentence and excuse a genuine claim.
_NEGATION_WINDOW = 60


def _overclaims(text: str) -> bool:
    low = text.lower()
    for phrase in _OVERCLAIM_PHRASES:
        start = low.find(phrase)
        while start != -1:
            window = low[max(0, start - _NEGATION_WINDOW):start]
            if not any(n in window for n in _NEGATORS):
                return True          # an affirmative claim, with nothing negating it
            start = low.find(phrase, start + 1)
    return False


#: Phrases that would undo a passing verdict. On a clean machine the model kept
#: writing "the check reports it clean, but three files remain... these should be
#: removed before selling" -- reading the details of PASSED checks as outstanding
#: work. A seller acting on that would wipe an already-wiped machine; a buyer
#: reading it would distrust a passport that had in fact passed.
_CONTRADICTION_PHRASES = (
    "not clean", "still remain", "remain on", "items remain", "should be removed",
    "must be removed", "need to be removed", "not factory", "still present",
    "before selling", "before the machine is sold", "however, there",
)


def _contradicts(text: str, status: str) -> bool:
    if status != "clean":
        return False
    low = text.lower()
    return any(p in low for p in _CONTRADICTION_PHRASES)


def check(clean_state: dict[str, Any] | None,
          today: dt.date | None = None) -> dict[str, Any]:
    """Judge one collector `clean_state` block."""
    today = today or dt.date.today()

    if not clean_state or not clean_state.get("checked"):
        return WipeCheck(
            status="unknown",
            note="The scan couldn't read this device's user folders, so nothing can be "
                 "confirmed either way. Run the deep scan again, as administrator.",
        ).as_dict()

    checks: list[dict[str, Any]] = []
    failures: list[str] = []

    def evaluate(key: str, label: str, limit: int, singular: str, plural: str,
                 capped_key: str | None = None) -> None:
        value = clean_state.get(key)
        if value is None:
            checks.append(_check(label, None, "couldn't be read"))
            return
        ok = value <= limit
        word = singular if value == 1 else plural
        # The collector stops counting files once it passes the cap, because the
        # exact number is irrelevant to a threshold test and expensive to compute.
        # Report it as "30+" rather than as a total it isn't.
        capped = bool(capped_key and clean_state.get(capped_key))
        checks.append(_check(label, ok, f"{value}{'+' if capped else ''} {word}"))
        if not ok:
            failures.append(label)

    evaluate("user_profiles", "No leftover accounts", MAX_CLEAN_PROFILES,
             "account on this PC", "accounts on this PC")
    evaluate("user_files", "Personal folders empty", MAX_CLEAN_FILES,
             "file in Desktop/Documents/Downloads", "files in Desktop/Documents/Downloads",
             capped_key="user_files_capped")
    evaluate("wifi_profiles", "No saved Wi-Fi networks", MAX_CLEAN_WIFI,
             "saved network", "saved networks")
    evaluate("installed_apps", "No leftover software", MAX_CLEAN_APPS,
             "installed program", "installed programs")

    days = clean_state.get("os_install_days")
    if days is None:
        checks.append(_check("Windows recently reset", None, "install date couldn't be read"))
    else:
        ok = days <= MAX_CLEAN_INSTALL_DAYS
        checks.append(_check("Windows recently reset", ok, f"installed {days:.0f} days ago"))
        if not ok:
            failures.append("Windows recently reset")

    # An unreadable field is never a pass. Requiring every check to be explicitly
    # True means a partial read reports "unknown" rather than quietly certifying a
    # machine on the strength of the two probes that happened to work.
    if any(c["ok"] is None for c in checks):
        return WipeCheck(
            status="unknown", checks=checks, failures=failures,
            note="Some checks couldn't be read, so this can't be confirmed either way.",
        ).as_dict()

    if failures:
        return WipeCheck(
            status="not_clean", checks=checks, failures=failures,
            note="This device still looks like it belongs to someone. Run the reset in the "
                 "steps above, then scan again — nothing is recorded on the passport until "
                 "it comes back clean.",
        ).as_dict()

    return WipeCheck(
        status="clean", checks=checks,
        verified_at=today.isoformat(),
        note="Every check passed: this device looks factory-fresh. That is a check of what's "
             "visible, not a forensic guarantee that deleted data is unrecoverable.",
    ).as_dict()
