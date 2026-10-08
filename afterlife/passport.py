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
def scan_device_id(scan: dict[str, Any]) -> str:
    seed = f"{scan.get('os')}|{scan.get('gpu')}|{scan.get('cpu_cores')}|{scan.get('ram_gb')}|{scan.get('architecture')}"
    return "AFL-" + base64.b32encode(hashlib.sha256(seed.encode()).digest()).decode()[:10]


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


def verify_payload(doc: dict[str, Any]) -> bool:
    """Re-builds the same VC envelope from the doc's own stored fields and
    checks it against the stored signature. False if anything was edited."""
    try:
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
                "fault_described": bool(problem.strip()),
                "prediction": pred["prediction"],
                "eol_risk": pred["eol_risk"],
                "probabilities": pred["probabilities"],
                "basis": "fault + population prior" if problem.strip() else "population prior (no fault given)",
            }
        except Exception:
            pass  # model unavailable — passport still issues without the outlook

    return sign_payload(profile)
