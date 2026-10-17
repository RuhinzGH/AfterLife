"""What the law entitles this device's owner to, for repair.

Directive (EU) 2024/1799 (the "right to repair" directive) applies across EU
member states from 31 July 2026. For products in its scope, the maker must repair
on request, at a reasonable price, after the legal guarantee has run out.

Scope is the hard part. The obligation covers only products that already carry
reparability requirements under EU ecodesign law (the directive's Annex II).
Phones and tablets are on that list; electronic displays are; laptops, desktops
and games consoles as whole products are not. Telling a laptop owner they have
an entitlement they do not have would be confident, plausible and harmful, so
the most common case here says "not covered" first.

Every statement below is about published EU law and names its source. It is not
legal advice, and it applies in the EU and EEA only: outside it, the card says
so instead of showing EU rules.
"""
from __future__ import annotations

import datetime as dt
from typing import Any

APPLIES_FROM = dt.date(2026, 7, 31)

SRC_REPAIR = "Directive (EU) 2024/1799 on the repair of goods"
SRC_GUARANTEE = "Directive (EU) 2019/771 (legal guarantee on goods)"
SRC_PHONES = "Regulation (EU) 2023/1670 (ecodesign for phones and tablets)"
URL_REPAIR = "https://commission.europa.eu/law/law-topic/consumer-protection-law/directive-repair-goods_en"
URL_PHONES = "https://eur-lex.europa.eu/eli/reg/2023/1670/oj"
URL_INDIA = "https://righttorepairindia.gov.in/"

#: The app's device types against the directive's scope. "display_only": the
#: screen inside is covered (electronic displays), the machine is not.
SCOPE: dict[str, str] = {
    "Mobile": "covered",
    "Tablet": "covered",
    "Laptop": "display_only",
    "Desktop computer": "not_covered",
    "Games console": "not_covered",
}

_PLURAL = {"Mobile": "Mobile phones", "Tablet": "Tablets", "Laptop": "Laptops",
           "Desktop computer": "Desktop computers", "Games console": "Games consoles"}

_GUARANTEE = {
    "title": "Within two years of buying it new, the seller must fix it for free",
    "detail": "Every EU country gives at least a two-year legal guarantee on goods: a fault "
              "present at delivery must be repaired or replaced at no cost. If you choose "
              "repair, the guarantee is extended by 12 months.",
    "source": f"{SRC_GUARANTEE}, as amended by {SRC_REPAIR}",
}


def _covered_rights(category: str) -> list[dict[str, str]]:
    rights = [
        {"title": "The maker must repair it, even after the guarantee",
         "detail": "On request, at a reasonable price and within a reasonable time.",
         "source": SRC_REPAIR},
        {"title": "Repair cannot be blocked",
         "detail": "Contract terms, hardware or software techniques that stop independent "
                   "repairers or second-hand parts are not allowed without a legitimate reason.",
         "source": SRC_REPAIR},
        {"title": "A written repair quote holds for 30 days",
         "detail": "If a repairer gives you the European Repair Information Form, its price "
                   "and conditions stay fixed for 30 days, so you can compare.",
         "source": SRC_REPAIR},
    ]
    if category in ("Mobile", "Tablet"):
        rights += [
            {"title": "Spare parts for seven years",
             "detail": "Key parts must stay available for seven years after the model stops "
                       "being sold, delivered within 5 to 10 working days.",
             "source": SRC_PHONES},
            {"title": "At least five years of operating-system updates",
             "detail": "Counted from when the model stops being sold, not from when you bought yours.",
             "source": SRC_PHONES},
        ]
    return rights


def assess(product_category: str | None, in_eea: bool | None, country: str | None = None,
           country_name: str | None = None, today: dt.date | None = None) -> dict[str, Any] | None:
    """The owner's repair entitlements. None for an unknown device type: a device
    this module does not understand gets no claim at all."""
    category = (product_category or "").strip()
    status = SCOPE.get(category)
    if not status:
        return None
    today = today or dt.date.today()
    out: dict[str, Any] = {
        "category": category, "status": status, "jurisdiction": "EU and EEA",
        "applies_from": APPLIES_FROM.isoformat(), "in_force": today >= APPLIES_FROM,
        "country": country, "country_name": country_name,
        "sources": [{"label": SRC_REPAIR, "url": URL_REPAIR}], "rights": [],
    }

    if in_eea is False:
        where = country_name or "your country"
        out["status"] = "outside"
        out["headline"] = f"EU repair rules don't apply in {where}"
        out["rights"] = [{
            "title": "This app holds repair rules for the EU and EEA only",
            "detail": f"It makes no claim about what the law in {where} entitles you to; your "
                      f"seller's warranty and local consumer law still apply. The country comes "
                      f"from this browser's time zone.",
            "source": "",
        }]
        if country == "IN":
            out["rights"].append({
                "title": "India: the government's Right to Repair Portal",
                "detail": "Run by the Department of Consumer Affairs, it gathers brands' manuals, "
                          "spare-part prices and warranty information for sectors including mobile "
                          "phones and tablets and consumer durables. Brands join voluntarily, and it "
                          "is an information portal, not a legal right to repair.",
                "source": "Department of Consumer Affairs, Government of India"})
            out["sources"] = [{"label": "Right to Repair Portal India", "url": URL_INDIA}]
        return out

    label = _PLURAL[category]
    if status == "covered":
        out["headline"] = f"{label} are covered by the EU right to repair"
        out["rights"] = _covered_rights(category) + [_GUARANTEE]
        if category in ("Mobile", "Tablet"):
            out["sources"].append({"label": SRC_PHONES, "url": URL_PHONES})
    elif status == "display_only":
        out["headline"] = "Only this laptop's screen is covered, not the laptop"
        out["rights"] = [
            {"title": "The screen is in scope; the rest of the laptop is not",
             "detail": "The repair obligation follows products that have EU ecodesign "
                       "reparability rules. Electronic displays have them; laptops as a whole "
                       "do not yet. A screen repair is covered; a motherboard is not.",
             "source": SRC_REPAIR},
            _GUARANTEE,
            {"title": "This can change",
             "detail": "If laptops get ecodesign reparability rules, the repair obligation "
                       "will cover them as well, without any change to the device.",
             "source": SRC_REPAIR},
        ]
    else:
        out["headline"] = f"{label} are not covered by the EU right to repair yet"
        out["rights"] = [
            {"title": "Not in the current scope",
             "detail": "The repair obligation covers products such as phones, tablets, "
                       "electronic displays, washing machines, dishwashers, fridges and vacuum "
                       "cleaners. This type of device is not among them.",
             "source": SRC_REPAIR},
            _GUARANTEE,
        ]
    return out
