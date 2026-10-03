"""Issuer-key pinning: a valid signature by the wrong key is NOT AfterLife-issued.

Guards the core trust claim (afterlife/passport.issued_by_afterlife): a forger
can sign a fake passport with their own key and embed it, so a valid signature
alone must never read as "issued by AfterLife".
"""
import base64
import copy

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from afterlife import passport as P


def _genuine():
    return P.sign_payload({"device_id": "DEV-TEST", "make_model": "Dell", "age_years": 3.0})


def test_genuine_passport_verifies_and_is_afterlife_issued():
    doc = _genuine()
    assert P.verify_payload(doc) is True
    assert P.issued_by_afterlife(doc) is True


def test_tampered_payload_fails_signature():
    doc = _genuine()
    doc = copy.deepcopy(doc)
    doc["payload"]["make_model"] = "Dell (edited)"
    assert P.verify_payload(doc) is False


def test_self_signed_forgery_verifies_but_is_not_afterlife_issued():
    """The whole point of pinning: a forger's own key passes the signature check
    but must NOT be reported as issued by AfterLife."""
    doc = _genuine()
    atk = Ed25519PrivateKey.generate()
    atk_pub = base64.urlsafe_b64encode(
        atk.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    ).decode()
    env = P._vc_envelope(doc["payload"], "did:key:afterlife:FAKE", doc["validFrom"])
    forgery = {
        **env, "payload": doc["payload"], "issuer": "did:key:afterlife:FAKE",
        "validFrom": doc["validFrom"],
        "signature": base64.urlsafe_b64encode(atk.sign(P._canonical(env))).decode(),
        "issuer_pubkey": atk_pub,
    }
    assert P.verify_payload(forgery) is True          # signature is internally valid
    assert P.issued_by_afterlife(forgery) is False     # but not our key
