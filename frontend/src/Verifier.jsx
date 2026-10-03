import { useEffect, useRef, useState } from "react";
import jsQR from "jsqr";
import { api } from "./api.js";
import PassportCard from "./PassportCard.jsx";
import { b64decodeUtf8, b64decodeCompressed } from "./b64.js";

const MODE = { camera: "camera", upload: "upload", paste: "paste" };

// Input may be raw passport JSON, or a URL like ...?verify=<base64url(json)>.
// The verify value is URL-safe base64 (no +, /, = to worry about), so no
// percent-decoding is needed — but tolerate it anyway in case the text was
// copied from somewhere that percent-encoded it (e.g. a browser address bar).
function extractPassport(text) {
  const t = text.trim();
  const m = t.match(/[?&]verify=([^&\s]+)/);
  if (m) {
    let raw = m[1];
    try { raw = decodeURIComponent(raw); } catch { /* wasn't percent-encoded */ }
    // Gzip-compressed is the current format; plain base64 is the pre-compression
    // format, kept as a fallback so links/QRs generated before this change (or
    // saved PNGs from that era) still verify instead of silently breaking.
    try { return b64decodeCompressed(raw); } catch { /* fall through */ }
    try { return JSON.parse(b64decodeUtf8(raw)); } catch { /* fall through */ }
  }
  try { return JSON.parse(t); } catch { return null; }
}

export default function Verifier({ onNavigate }) {
  // Captured once, on the very first render -- before the effect below strips
  // "?verify=" from the URL. A QR scan should land straight on its result, not
  // on the upload/camera/paste chooser with the result buried below a scroll.
  const [fromQrLink, setFromQrLink] = useState(() => window.location.search.includes("verify="));
  const [mode, setMode] = useState(MODE.upload);
  const [doc, setDoc] = useState(null);
  const [result, setResult] = useState(null);
  const [err, setErr] = useState(null);
  const [text, setText] = useState("");
  const [scanning, setScanning] = useState(false);
  const fileRef = useRef(null);
  const videoRef = useRef(null);
  const streamRef = useRef(null);
  const rafRef = useRef(null);

  // Auto-verify if the page was opened from a QR link (?verify=...)
  useEffect(() => {
    if (window.location.search.includes("verify=")) {
      const p = extractPassport(window.location.search);
      if (p) runVerify(p);
      else setErr("Couldn't read the passport from this link — it may be incomplete. Try the QR again or ask for a fresh share.");
      window.history.replaceState({}, "", window.location.pathname);
    }
    return () => stopCamera();
  }, []);

  function stopCamera() {
    cancelAnimationFrame(rafRef.current);
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    setScanning(false);
  }

  async function startCamera() {
    setErr(null); setDoc(null); setResult(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" } });
      streamRef.current = stream;
      const v = videoRef.current;
      v.srcObject = stream;
      await v.play();
      setScanning(true);
      tick();
    } catch (e) {
      setErr("Camera unavailable: " + e.message + ". Try uploading a QR image or pasting instead.");
    }
  }

  function tick() {
    const v = videoRef.current;
    if (!v || v.readyState !== v.HAVE_ENOUGH_DATA) {
      rafRef.current = requestAnimationFrame(tick);
      return;
    }
    const canvas = document.createElement("canvas");
    canvas.width = v.videoWidth; canvas.height = v.videoHeight;
    const ctx = canvas.getContext("2d");
    ctx.drawImage(v, 0, 0, canvas.width, canvas.height);
    const img = ctx.getImageData(0, 0, canvas.width, canvas.height);
    const code = jsQR(img.data, img.width, img.height);
    if (code) {
      stopCamera();
      const p = extractPassport(code.data);
      if (p) runVerify(p);
      else setErr("QR scanned, but it isn't an Afterlife passport.");
    } else {
      rafRef.current = requestAnimationFrame(tick);
    }
  }

  async function runVerify(passport) {
    try {
      const res = await api.verify(passport);
      setDoc(passport);
      setResult(res);
    } catch (e) { setErr(e.message); }
  }

  function handleFile(e) {
    const file = e.target.files?.[0];
    if (!file) return;
    setErr(null); setDoc(null); setResult(null);
    const img = new Image();
    img.onload = () => {
      const canvas = document.createElement("canvas");
      canvas.width = img.naturalWidth; canvas.height = img.naturalHeight;
      const ctx = canvas.getContext("2d");
      ctx.drawImage(img, 0, 0);
      const data = ctx.getImageData(0, 0, canvas.width, canvas.height);
      const code = jsQR(data.data, data.width, data.height);
      URL.revokeObjectURL(img.src);
      if (!code) { setErr("Couldn't find a QR code in that image. Try a clearer screenshot or photo."); return; }
      const p = extractPassport(code.data);
      if (p) runVerify(p);
      else setErr("QR found, but it isn't an Afterlife passport.");
    };
    img.onerror = () => setErr("Couldn't read that image file.");
    img.src = URL.createObjectURL(file);
    e.target.value = "";
  }

  function verifyPasted() {
    setErr(null); setDoc(null); setResult(null);
    const p = extractPassport(text);
    if (!p) { setErr("That isn't a valid passport or verify link."); return; }
    runVerify(p);
  }

  function reset() {
    stopCamera(); setDoc(null); setResult(null); setErr(null); setText("");
  }

  function switchMode(m) {
    stopCamera(); setMode(m); setDoc(null); setResult(null); setErr(null);
  }

  // Landed here from a QR scan and it already checked out -- skip straight to the
  // result, no upload/camera/paste chooser above it and nothing to scroll past.
  if (fromQrLink && doc) {
    return (
      <div className="view">
        <div>
          <div className="eyebrow">Passport verifier</div>
          <h1 className="title">
            {result?.valid && result?.issued_by_afterlife !== false
              ? <>Verified <span className="seal" aria-hidden="true">✓</span></>
              : "Signature check"}
          </h1>
          <p className="lede">This passport was opened from its QR code and checked automatically.</p>
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: "0.9rem", maxWidth: "560px" }}>
          <VerifyVerdict result={result} />
          <PassportCard doc={doc} verified={result?.valid && result?.issued_by_afterlife !== false} />
          <div style={{ display: "flex", gap: "0.7rem", flexWrap: "wrap" }}>
            <button className="cta" onClick={() => onNavigate?.("scan")}>Scan your own device</button>
            <button className="ghost" onClick={() => { reset(); setFromQrLink(false); }}>Verify a different passport</button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="view">
      <div>
        <div className="eyebrow">Passport verifier</div>
        <h1 className="title">Don't buy on hopes and vibes</h1>
        <p className="lede">
          Scan an Afterlife passport QR using your phone and it opens the website right there, with
          all the details of that passport already verified. You can also point this device's own
          camera at a QR, upload a saved QR image, or paste the passport text directly.
        </p>
        <p className="note-strip" style={{ marginTop: "0.6rem" }}>
          Don't attempt to edit or tamper with a passport — even a single changed detail invalidates
          it instantly and it will no longer show as verified.
        </p>
      </div>

      <div className="seg">
        <button className={mode === MODE.camera ? "on" : ""} onClick={() => switchMode(MODE.camera)}>📷 Camera</button>
        <button className={mode === MODE.upload ? "on" : ""} onClick={() => switchMode(MODE.upload)}>📁 Upload QR</button>
        <button className={mode === MODE.paste ? "on" : ""} onClick={() => switchMode(MODE.paste)}>⌨ Paste</button>
      </div>

      {err && <div className="badge bad">⚠ {err}</div>}

      <div className={`grid ${doc ? "g-115" : ""}`} style={{ alignItems: "start" }}>
        <div className="card pad-lg">
          {mode === MODE.camera && (
            <div className="cam-wrap">
              <div className="cam-frame">
                <video ref={videoRef} playsInline muted />
                {scanning && <div className="cam-reticle" />}
                {!scanning && <div className="cam-placeholder">camera preview</div>}
              </div>
              {!scanning
                ? <button className="cta" onClick={startCamera}>Start camera</button>
                : <button className="ghost" onClick={stopCamera}>Stop camera</button>}
              <p className="note">Hold a passport QR up to the camera — it detects and verifies automatically.</p>
            </div>
          )}
          {mode === MODE.upload && (
            <div className="cam-wrap">
              <label className="dropzone" htmlFor="qr-file">
                <span className="dz-icon">📁</span>
                <span>Click to upload a QR code image</span>
                <span className="note">PNG or JPG — the passport QR you saved earlier</span>
              </label>
              <input id="qr-file" ref={fileRef} type="file" accept="image/*" onChange={handleFile} style={{ display: "none" }} />
            </div>
          )}
          {mode === MODE.paste && (
            <div className="form">
              <div className="field">
                <label>Passport or verify link</label>
                <textarea style={{ minHeight: "10rem", fontFamily: "var(--mono)", fontSize: "0.76rem" }}
                  value={text} onChange={(e) => setText(e.target.value)}
                  placeholder='paste the passport JSON, or a ...?verify=... link' />
              </div>
              <button className="cta" onClick={verifyPasted} disabled={!text.trim()}>Verify</button>
            </div>
          )}
        </div>

        {doc && (
          <div style={{ display: "flex", flexDirection: "column", gap: "0.9rem" }}>
            <VerifyVerdict result={result} />
            <PassportCard doc={doc} verified={result?.valid && result?.issued_by_afterlife !== false} />
            <button className="ghost" onClick={reset} style={{ alignSelf: "flex-start" }}>Verify another</button>
          </div>
        )}
      </div>
    </div>
  );
}

// The verdict, spelled out in C2PA's vocabulary.
//
// The logic here was already right: a valid signature by an UNKNOWN key is not
// a genuine passport, only an internally consistent document, so a self-signed
// forgery gets amber rather than the green seal. What was missing was the
// language to explain that to somebody who is not a cryptographer.
//
// C2PA -- the Content Credentials standard, which solves exactly this problem
// for media -- separates what a check VALIDATES from what it merely records as
// ASSERTED. That distinction is the whole of AfterLife's trust story and
// VERIFICATION.md already draws it in a table; the UI just never said it out
// loud. A buyer looking at a second-hand laptop needs three things in this
// order: what is proven, what is NOT proven, and what to do about it.
//
// The third one matters most and is the one most verifiers omit. "Signature
// valid" is not an instruction.
export const VERDICTS = {
  tampered: {
    tone: "bad",
    label: "Tampered",
    validated: null,
    asserted: "Nothing. The signature does not match the contents, so every "
              + "figure in this document is unsupported.",
    action: "Do not rely on anything this passport claims. Ask the seller to "
            + "re-scan the device and issue a fresh one.",
  },
  unknown_issuer: {
    tone: "warn",
    label: "Self-signed — not AfterLife",
    validated: "That this document has not been altered since it was signed.",
    asserted: "Who signed it. The key it carries is not AfterLife's, so anyone "
              + "could have generated a keypair and signed these claims "
              + "themselves. Internally consistent is not the same as genuine.",
    action: "Treat the specifications as unverified. A real AfterLife passport "
            + "is signed by the one published issuer key.",
  },
  genuine: {
    tone: "good",
    label: "Issued by AfterLife",
    validated: "That AfterLife issued this passport, and that not one character "
               + "has changed since — specifications, score, date and issuer alike.",
    asserted: "That the scan read true hardware. The signature proves the "
              + "document is intact, not that the machine was honest with it. "
              + "Closing that gap needs TPM-rooted attestation.",
    action: "You can rely on these figures being the ones AfterLife computed.",
  },
  valid_unpinned: {
    tone: "good",
    label: "Signature valid",
    validated: "That this document has not been altered since it was signed.",
    asserted: "Who issued it. No trusted key was available to check against, so "
              + "this cannot yet be distinguished from a self-signed document.",
    action: "Fetch AfterLife's published key and re-check to confirm the issuer.",
  },
};

export function verdictFor(result) {
  if (!result.valid) return VERDICTS.tampered;
  if (result.issued_by_afterlife === false) return VERDICTS.unknown_issuer;
  if (result.issued_by_afterlife === true) return VERDICTS.genuine;
  return VERDICTS.valid_unpinned;
}

function VerifyVerdict({ result }) {
  if (!result) return null;
  const v = verdictFor(result);
  return (
    <div className={`verify-verdict ${v.tone}`} role="status">
      <div className="verify-verdict-head">
        <span className="verify-verdict-tag">{v.label}</span>
        <span className="verify-verdict-msg">{result.message}</span>
      </div>

      <dl className="verify-proof">
        {v.validated && (
          <div className="vp-row is-yes">
            <dt>Proven</dt>
            <dd>{v.validated}</dd>
          </div>
        )}
        <div className="vp-row is-no">
          <dt>Not proven</dt>
          <dd>{v.asserted}</dd>
        </div>
        <div className="vp-row is-do">
          <dt>What to do</dt>
          <dd>{v.action}</dd>
        </div>
      </dl>
    </div>
  );
}
