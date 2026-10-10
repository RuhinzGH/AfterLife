"""Every copy of the data in a saved passport is covered by the signature.

A saved passport holds the device data twice (`credentialSubject`, the W3C
shape, and `payload`) and the signature twice (`proof.proofValue` and
`signature`). Testing found that editing the first copy -- the one Notepad
finds first -- still verified, because only `payload` was checked. These tests
edit the file the way a person would: as JSON text, after a round trip, so the
two copies are separate objects as they are on disk.
"""
import json

from afterlife import passport as P


def _saved():
    doc = P.build_scan_passport({"os": "Windows 11", "gpu": "Intel Iris Xe", "cpu_cores": 8,
                                 "ram_gb": 8, "architecture": "x86 64", "product_category": "Laptop"})
    return json.dumps(doc, indent=2)   # exactly what "Save passport (JSON)" writes


def test_untouched_saved_file_verifies():
    assert P.verify_payload(json.loads(_saved())) is True


def test_editing_the_first_copy_in_a_text_editor_fails():
    text = _saved()
    assert text.count('"ram_gb": 8') == 2
    edited = json.loads(text.replace('"ram_gb": 8', '"ram_gb": 32', 1))
    assert P.verify_payload(edited) is False


def test_editing_either_copy_fails():
    for key in ("credentialSubject", "payload"):
        doc = json.loads(_saved())
        doc[key]["ram_gb"] = 32
        assert P.verify_payload(doc) is False, key


def test_editing_the_proof_block_fails():
    for field, value in (("proofValue", "AAAA"), ("verificationMethod", "did:key:someone-else"),
                         ("created", "2020-01-01T00:00:00+00:00")):
        doc = json.loads(_saved())
        doc["proof"][field] = value
        assert P.verify_payload(doc) is False, field


def test_editing_context_or_type_fails():
    doc = json.loads(_saved()); doc["type"] = ["VerifiableCredential"]
    assert P.verify_payload(doc) is False
    doc = json.loads(_saved()); doc["@context"] = ["https://example.org"]
    assert P.verify_payload(doc) is False


def test_qr_link_shape_without_duplicates_still_verifies():
    doc = json.loads(_saved())
    qr = {k: doc[k] for k in ("payload", "signature", "issuer_pubkey", "issuer", "validFrom")}
    assert P.verify_payload(qr) is True
