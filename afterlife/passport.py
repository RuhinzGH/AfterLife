"""Device passport — a signed, verifiable record of one browser scan.

Turns a browser scan (plus the age and fault the user adds) into a payload,
wraps it in a W3C Verifiable Credential envelope, and signs it with Ed25519.
The signature is what makes it "not vibes" — a buyer can verify the facts were
not edited after issue. Anyone can forge a *claim*; nobody can forge a
*signature* without the issuer's private key.
"""
from __future__ import annotations

import base64
import hashlib
import datetime as dt
import json
import os
import re
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

KEY_DIR = Path(os.environ.get("AFTERLIFE_KEY_DIR") or Path(__file__).resolve().parent.parent / "data" / "keys")
KEY_DIR.mkdir(parents=True, exist_ok=True)
_PRIV = KEY_DIR / "issuer_ed25519.key"
_PUB = KEY_DIR / "issuer_ed25519.pub"

# ----------------------------------------------------------------- keys
def _load_or_create_keys() -> tuple[Ed25519PrivateKey, Ed25519PublicKey]:
    # On hosts with no persistent disk (e.g. Render's free tier), the key must
    # survive container restarts via a secret env var instead of a file.
    if pem_b64 := os.environ.get("AFTERLIFE_PRIVATE_KEY_B64"):
        priv = serialization.load_pem_private_key(base64.b64decode(pem_b64), password=None)
    elif _PRIV.exists():
        priv = serialization.load_pem_private_key(_PRIV.read_bytes(), password=None)
    else:
        priv = Ed25519PrivateKey.generate()
        _PRIV.write_bytes(priv.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption()))
        pub = priv.public_key()
        _PUB.write_bytes(pub.public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo))
    return priv, priv.public_key()


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode()


# ------------------------------------------------------------- device identity
# A fingerprint of what the browser can see, never a timestamp, so repeat scans
# of the same browser and machine get the same id.
# The id is a digest of the whole seed. It used to be the first 10 characters of
# the seed's base64 -- just its first 7 letters re-spelled -- so every Windows
# scan ("Windows 11|...") got AFL-V2LUZG93CY. Base32 keeps the AFL- + 10
# uppercase characters format.
def _id_from_seed(seed: str) -> str:
    return "AFL-" + base64.b32encode(hashlib.sha256(seed.encode()).digest()).decode()[:10]


def scan_device_id(scan: dict[str, Any]) -> str:
    seed = f"{scan.get('os')}|{scan.get('gpu')}|{scan.get('cpu_cores')}|{scan.get('ram_gb')}|{scan.get('architecture')}"
    return _id_from_seed(seed)


def deep_device_id(device: dict[str, Any]) -> str:
    """A deep scan reads real hardware identity, so its ID comes from maker |
    model | CPU, hashed the same way as scan_device_id (defect D7): a plain
    prefix of the seed would give every laptop from one maker the same ID."""
    seed = f"{device.get('manufacturer')}|{device.get('model')}|{device.get('cpu_name')}"
    return _id_from_seed(seed)


# --------------------------------------------------------- issuer key pinning
# A signature check alone only proves a passport is INTERNALLY consistent: the
# doc carries its own issuer_pubkey, so a forger can generate a fresh keypair,
# sign a fake passport with it, embed that key, and it verifies. "Issued by
# AfterLife" is a stronger, separate claim -- the passport must be signed by the
# ONE key AfterLife publishes out-of-band (this endpoint, the docs, the repo),
# which a verifier pins against instead of trusting the key the passport asserts
# about itself.
def issuer_public_key_b64() -> str | None:
    """The issuer's public key (raw, url-safe base64) -- the value verifiers pin
    against. Derived from whatever key this instance actually signs with, so it
    is always correct for the running backend."""
    try:
        _, pub = _load_or_create_keys()
        return _b64(pub.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw))
    except Exception:
        return None


def trusted_issuer_pubkey() -> str | None:
    """The public key a passport MUST carry to count as genuinely AfterLife-issued.
    Prefers an explicit AFTERLIFE_ISSUER_PUBKEY (lets a verifier pin a key it was
    told out-of-band, even one a different signer produced); otherwise falls back
    to this instance's own signing key, so the real backend pins against itself."""
    env = os.environ.get("AFTERLIFE_ISSUER_PUBKEY", "").strip()
    return env or issuer_public_key_b64()


def issued_by_afterlife(doc: dict[str, Any]) -> bool | None:
    """True if the passport is signed by the trusted issuer key, False if it is
    signed by some other key (a self-signed forgery), None if no trusted key is
    available to pin against. Independent of the signature check itself."""
    trusted = trusted_issuer_pubkey()
    if not trusted:
        return None
    return doc.get("issuer_pubkey") == trusted


# ---------------------------------------------------------------- browser scan
def _normalize(v: Any) -> Any:
    """Make the payload's numbers round-trip-stable across Python <-> JavaScript.

    JS has no distinct float type, so a Python 3.0 that FastAPI serializes as "3.0"
    comes back through the browser (JSON.parse -> 3 -> JSON.stringify) as "3". If we
    sign the bytes for "3.0" and later canonicalize "3", the signature falsely reads
    invalid. Collapsing whole-number floats to ints on BOTH sign and verify removes
    that distinction so an untouched passport always verifies.
    """
    if isinstance(v, bool):
        return v
    if isinstance(v, float) and v.is_integer() and abs(v) < 1e15:
        return int(v)
    if isinstance(v, dict):
        return {k: _normalize(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_normalize(x) for x in v]
    return v


def _canonical(payload: dict[str, Any]) -> bytes:
    return json.dumps(_normalize(payload), sort_keys=True, separators=(",", ":")).encode()


# The W3C Verifiable Credentials envelope every real Digital Product Passport
# implementation uses (UN Transparency Protocol, Eclipse Tractus-X) --
# @context/type/issuer/validFrom/credentialSubject/proof. This is
# shape-compatible with that ecosystem, not a full VC-spec cryptographic
# implementation: the proof below covers this module's own canonical JSON
# (sorted keys, no whitespace, see _canonical()), not JSON-LD RDF
# canonicalization (URDNA2015) -- disclosed here rather than implied, same as
# every other approximation in this codebase. What IS real: Ed25519 signing
# and verification, and the proof covers the ENTIRE envelope (context, type,
# issuer, validFrom -- not just the device data), so none of those claims can
# be edited post-issue without invalidating the signature either.
VC_CONTEXT = [
    "https://www.w3.org/ns/credentials/v2",
    "https://www.w3.org/ns/credentials/examples/v2",
]


def _vc_envelope(payload: dict[str, Any], issuer: str | None, valid_from: str | None) -> dict[str, Any]:
    """Exactly what gets signed -- everything in the credential except the
    proof block itself, so the proof is tamper-evident over the whole
    document, not just credentialSubject."""
    return {
        "@context": VC_CONTEXT,
        "type": ["VerifiableCredential", "DigitalProductPassport"],
        "issuer": issuer,
        "validFrom": valid_from,
        "credentialSubject": payload,
    }


def sign_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Ed25519-sign an arbitrary dict, shaped as a W3C Verifiable Credential.

    `payload`/`signature`/`issuer_pubkey` are also kept at the top level, so the
    passport card and the verifier read one simple shape.
    """
    priv, pub = _load_or_create_keys()
    pubkey_b64 = _b64(pub.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw))
    issuer = f"did:key:afterlife:{pubkey_b64[:16]}"
    valid_from = dt.datetime.now(dt.timezone.utc).isoformat()
    envelope = _vc_envelope(payload, issuer, valid_from)
    signature = _b64(priv.sign(_canonical(envelope)))
    doc = {
        **envelope,
        "proof": {
            "type": "Ed25519Signature2020",
            "created": valid_from,
            "verificationMethod": issuer,
            "proofPurpose": "assertionMethod",
            "proofValue": signature,
        },
        "payload": payload,
        "signature": signature,
        "issuer_pubkey": pubkey_b64,
    }
    return doc


def _copies_agree(doc: dict[str, Any]) -> bool:
    """A saved passport carries the device data twice: `credentialSubject` (the
    W3C shape) and `payload` (the simple shape the app reads), plus the signature
    twice (`proof.proofValue` and `signature`). Only one copy of each is checked
    against the signature, so every other copy present must match it exactly --
    otherwise someone could edit the copy a reader looks at first and the
    passport would still verify. A QR link carries only the checked copies, so
    absent fields are fine; a present-but-different one is tampering."""
    if "credentialSubject" in doc and _normalize(doc["credentialSubject"]) != _normalize(doc["payload"]):
        return False
    if "@context" in doc and doc["@context"] != VC_CONTEXT:
        return False
    if "type" in doc and doc["type"] != ["VerifiableCredential", "DigitalProductPassport"]:
        return False
    if "proof" in doc:
        proof = doc["proof"]
        if not isinstance(proof, dict) or proof.get("proofValue") != doc["signature"]:
            return False
        if "verificationMethod" in proof and proof["verificationMethod"] != doc.get("issuer"):
            return False
        if "created" in proof and proof["created"] != doc.get("validFrom"):
            return False
    return True


def verify_payload(doc: dict[str, Any]) -> bool:
    """Re-builds the same VC envelope from the doc's own stored fields and
    checks it against the stored signature. False if anything was edited,
    including a duplicate copy of the data (see _copies_agree)."""
    try:
        if not _copies_agree(doc):
            return False
        pub = Ed25519PublicKey.from_public_bytes(base64.urlsafe_b64decode(doc["issuer_pubkey"]))
        sig = base64.urlsafe_b64decode(doc["signature"])
        envelope = _vc_envelope(doc["payload"], doc.get("issuer"), doc.get("validFrom"))
        pub.verify(sig, _canonical(envelope))
        return True
    except Exception:
        return False


def build_scan_passport(scan: dict[str, Any]) -> dict[str, Any]:
    """Turn a browser scan (+ optional user-supplied lifecycle inputs) into a signed passport.

    Honest about depth: browser scans see hardware identity and health signals but not
    TPM / disk SMART, so this is a 'profile' tier, upgradeable via the collector. If the
    user supplies device age (and optionally a fault), the ML lifecycle model is run and
    its prediction is embedded in the *signed* payload — so the outlook is tamper-evident too.
    """
    # Deliberately excludes scanned_at -- a browser can't read a real hardware serial, so this is a fingerprint of
    # what it CAN see (os/gpu/cores/ram/architecture) rather than true identity,
    # but it's still stable across repeat scans of the same browser+machine,
    # which a timestamp-inclusive seed could never be.
    device_id = scan_device_id(scan)

    seen = [k for k in ("os", "gpu", "cpu_cores", "ram_gb", "architecture", "screen")
            if scan.get(k) not in (None, "")]
    completeness = round(100 * len(seen) / 6)

    profile = {
        "device_id": device_id,
        "tier": "browser profile",
        "issued": dt.date.today().isoformat(),
        "product_category": scan.get("product_category"),
        "os": scan.get("os"),
        "gpu": scan.get("gpu"),
        "gpu_vendor": scan.get("gpu_vendor"),
        "cpu_cores": scan.get("cpu_cores"),
        "ram_gb": scan.get("ram_gb"),
        "architecture": scan.get("architecture"),
        "screen": scan.get("screen"),
        "timezone": scan.get("timezone"),
        "windows_major": scan.get("win_major"),
        "completeness_pct": completeness,
        "note": "Profile tier — deep fields (TPM, disk health, battery wear) need the "
                "collector for a full verified passport.",
    }

    # Optional ML lifecycle outlook, if the user gave the inputs the browser can't see.
    age = scan.get("device_age")
    category = scan.get("product_category") or "Laptop"
    problem = scan.get("problem") or ""
    from .fault_lexicon import fault_themes
    themes = fault_themes(problem)
    if age not in (None, ""):
        try:
            from .predict import predict_lifecycle
            pred = predict_lifecycle(
                product_category=category,
                brand=scan.get("brand") or "Unknown",
                country=scan.get("country") or "Unknown",
                device_age=float(age),
                problem=problem,
            )
            profile["lifecycle"] = {
                "device_age": float(age),
                "product_category": category,
                # Only a recognised fault counts towards the score's fault
                # adjustment; the model still reads the words either way.
                "fault_described": bool(themes),
                "fault_themes": themes,
                "prediction": pred["prediction"],
                "eol_risk": pred["eol_risk"],
                "probabilities": pred["probabilities"],
                "basis": "fault + population prior" if problem.strip() else "population prior (no fault given)",
            }
        except Exception:
            pass  # model unavailable — passport still issues without the outlook

    return sign_payload(profile)


# ---------------------------------------------------------------- deep scan
# A deep scan runs the collector (collector/collect_device.ps1) on the machine
# itself, so it can measure what a browser cannot: Windows 11 readiness (CPU,
# TPM, Secure Boot), the operating system's support state, disk health, battery
# wear and age. Those measurements replace the fixed 75 a browser scan starts
# from. The weights below are chosen by design, not fitted -- they add up to 100
# and every sub-score is shown on the passport, so the number can be checked.
#
# Each fact is counted once. The trust score is hardware condition only; the
# operating system's support date is applied once, by the combined score
# (blend_score's support-horizon adjustment, which carries the real dates), and
# blend_score skips its own battery and age penalties when the trust score was
# measured, because both are already inside it.
UNKNOWN = "UNKNOWN"

DEEP_WEIGHTS = {"Windows 11 ready": 35, "Storage health": 25, "Battery health": 20, "Age": 20}


def _sub(name: str, points: int, note: str) -> dict[str, Any]:
    return {"name": name, "points": points, "max_points": DEEP_WEIGHTS[name], "note": note}


def _os_support(device: dict[str, Any]) -> str:
    """supported | esu | unsupported | unknown, from the same offline
    endoflife.date table the instant scan uses (no live call per scan)."""
    from .device_support import lookup
    horizon = lookup(None, str(device.get("os_caption") or ""))
    return "unknown" if horizon is None else horizon.support_state


def _storage(device: dict[str, Any]) -> tuple[int, str]:
    """The drive's own report, never a model: the NVMe critical-warning flag and
    rated write life used when the collector could read them, otherwise
    Windows' coarse HealthStatus."""
    nvme = next((d for d in (device.get("nvme_health") or []) if isinstance(d, dict)), None)
    if nvme and isinstance(nvme.get("critical_warning"), (int, float)):
        used = nvme.get("percentage_used")
        if nvme["critical_warning"]:
            return 5, "the drive is reporting a critical warning"
        if isinstance(used, (int, float)) and used >= 90:
            return 12, f"{used:.0f}% of rated write life used"
        return 25, (f"healthy, {used:.0f}% of rated write life used"
                    if isinstance(used, (int, float)) else "healthy (drive self-report)")
    health = str(device.get("disk_health") or "").strip()
    if health.lower() == "healthy":
        return 25, "healthy (Windows)"
    if health:
        return 10, f"{health} (Windows)"
    return 12, "not read"


def battery_points(health_pct: float) -> int:
    """The deep trust score's battery share (out of 20). Shared with uplift.py,
    so "replace the battery" is re-scored by the same rule that scored it."""
    return 20 if health_pct >= 80 else 13 if health_pct >= 60 else 7


def deep_trust_score(device: dict[str, Any]) -> tuple[int, list[dict[str, Any]], Any, str]:
    """Measured hardware trust (0-100) as five sub-scores, each shown."""
    from .win11 import assess as win11_assess
    elig = win11_assess(device)
    subs = []
    if elig.eligible is True:
        subs.append(_sub("Windows 11 ready", 35, "meets every Windows 11 requirement"))
    elif elig.eligible is None:
        subs.append(_sub("Windows 11 ready", 21, "not determined: the TPM could not be read (run as administrator)"))
    elif elig.permanently_blocked:
        subs.append(_sub("Windows 11 ready", 5, "blocked by the CPU generation (permanent)"))
    else:
        subs.append(_sub("Windows 11 ready", 16, "blocked by a firmware setting that can be switched on"))

    # Recorded on the passport as a fact, but not scored here: the combined
    # score applies the support date once (see the note above DEEP_WEIGHTS).
    state = _os_support(device)

    pts, note = _storage(device)
    subs.append(_sub("Storage health", pts, note))

    bh = device.get("battery_health_pct")
    if isinstance(bh, (int, float)):
        # 80% is a real industry bar: Amazon Renewed sells only devices whose
        # battery holds at least 80% of its original capacity.
        subs.append(_sub("Battery health", battery_points(bh), f"{bh:.0f}% of design capacity"))
    elif device.get("battery_present") is False:
        subs.append(_sub("Battery health", 20, "no battery (desktop)"))
    else:
        subs.append(_sub("Battery health", 10, "not read (run as administrator)"))

    age = device.get("approx_age_years")
    if isinstance(age, (int, float)):
        subs.append(_sub("Age", 20 if age <= 3 else 14 if age <= 5 else 8 if age <= 8 else 3,
                         f"about {age:.1f} years"))
    else:
        subs.append(_sub("Age", 10, "not determined"))
    return sum(s["points"] for s in subs), subs, elig, state


def deep_grade(score: int) -> str:
    """The same cut-offs as the blended score's grades, so one scale reads the same everywhere."""
    return ("A - excellent" if score >= 85 else "B - good" if score >= 70
            else "C - serviceable" if score >= 55 else "D - limited")


_GENERIC_FAMILY_NAMES = {"", "system product name", "not applicable", "to be filled by o.e.m.",
                         "default string", "system family", "n/a", "none"}
_CRYPTIC_PREFIX = re.compile(r"^[0-9A-Za-z]{2,10}_[0-9A-Za-z]{2,10}\s+")


def _friendly_name(device: dict[str, Any], make_model: str) -> str:
    """The retail name (e.g. "HP Victus") rather than a board code like "8A78",
    when the firmware reports a usable SystemFamily."""
    family = _CRYPTIC_PREFIX.sub("", (device.get("system_family") or "").strip()).strip()
    maker = (device.get("manufacturer") or "").strip()
    if not family or family.lower() in _GENERIC_FAMILY_NAMES or family.lower() == maker.lower():
        return make_model
    return f"{maker} {family}" if maker and maker.lower() not in family.lower() else family


def build_deep_passport(device: dict[str, Any]) -> dict[str, Any]:
    """A signed passport from a collector scan: the 'full scan' tier a browser
    profile can never reach, in the same signed shape, so the same card and the
    same verifier handle both."""
    from .scan_coverage import evaluate as evaluate_coverage
    from .win11 import Blocker
    from .wipe import check as wipe_check
    score, subs, elig, state = deep_trust_score(device)
    coverage = evaluate_coverage(device)
    make_model = f"{device.get('manufacturer') or '?'} {device.get('model') or '?'}".strip()
    bh = device.get("battery_health_pct")
    battery = (f"{bh:.0f}%" if isinstance(bh, (int, float))
               else "no battery" if device.get("battery_present") is False else UNKNOWN)
    payload = {
        "device_id": deep_device_id(device), "tier": "full scan", "issued": dt.date.today().isoformat(),
        "make_model": make_model, "device_name": _friendly_name(device, make_model),
        "manufacturer": device.get("manufacturer"),
        "os": f"{device.get('os_caption') or '?'} {device.get('os_release_id') or ''}".strip(),
        "os_support": state,
        "cpu": device.get("cpu_name"), "cpu_cores": device.get("cpu_cores"), "gpu": device.get("gpu_name"),
        "ram_gb": device.get("ram_gb"),
        "storage": f"{device.get('sysdrive_total_gb') or '?'} GB {device.get('disk_media_type') or ''}".strip(),
        "storage_health": next(s["note"] for s in subs if s["name"] == "Storage health"),
        "battery_health": battery,
        "win11": {True: "ELIGIBLE", False: "NOT ELIGIBLE", None: "INDETERMINATE"}[elig.eligible],
        "win11_blockers": [b.value for b in elig.blockers if b is not Blocker.UNKNOWN_TPM],
        "win11_note": (", ".join(b.value.replace("_", " ") for b in elig.blockers if b is not Blocker.UNKNOWN_TPM)
                       or ("the TPM could not be read (run as administrator)" if elig.eligible is None
                           else "meets every requirement")),
        "win11_permanently_blocked": elig.permanently_blocked,
        "win11_firmware_fixable": elig.firmware_fixable,
        "trust_score": score, "grade": deep_grade(score), "sub_scores": subs,
        "age_years": device.get("approx_age_years"),
        "completeness_pct": coverage["completeness_pct"], "scan_coverage": coverage,
        # A battery is the measured way to tell a laptop from a desktop; left
        # absent when the probe could not tell, rather than guessed.
        "product_category": ("Laptop" if device.get("battery_present") is True
                             else "Desktop computer" if device.get("battery_present") is False else None),
    }
    # persona_signals (which tools from a short fixed list are installed) is kept
    # OUT of the signed payload on purpose: a passport is handed to buyers, and a
    # buyer has no need to learn what software the seller runs. It rides beside
    # the passport for the usage-fit card instead (see api/main.py).
    wipe = wipe_check(device.get("clean_state"))
    if wipe.get("status") == "clean":
        # Inside the signature because it is the one field a second-hand buyer
        # is asked to trust; only a passing check is ever recorded.
        payload["wipe_verified"] = wipe.get("verified_at")
        payload["wipe_scope"] = "factory-fresh check, not forensic erasure"
    return sign_payload(payload)
