import { useEffect, useRef, useState } from "react";
import { api } from "./api.js";
import PassportCard from "./PassportCard.jsx";
import AssessmentDashboard from "./AssessmentDashboard.jsx";
import ReliabilitySignals from "./ReliabilitySignals.jsx";
import MitigationReport from "./MitigationReport.jsx";
import SecureBootAlert from "./SecureBootAlert.jsx";
import ScanProgress, { ScanCoverage } from "./ScanProgress.jsx";
import { b64encodeCompressed } from "./b64.js";
import { fetchAssessment } from "./assess.js";
import { markScanned } from "./deviceStore.js";
import { PLATFORM, allCommands, deepScanCommand, detectPlatform } from "./platform.js";

// The one-time code that pairs this page with the collector's upload. The
// server only accepts 16-64 URL-safe characters, so it cannot be guessed;
// crypto.getRandomValues is the browser's cryptographic generator.
function makeToken() {
  const bytes = crypto.getRandomValues(new Uint8Array(18));
  return [...bytes].map((b) => b.toString(16).padStart(2, "0")).join("");
}

export default function DeepScan({ onBack }) {
  const [token] = useState(makeToken);
  const [passport, setPassport] = useState(null);
  const [qr, setQr] = useState(null);
  const [assessment, setAssessment] = useState(null);
  const [copied, setCopied] = useState(false);
  const [waiting, setWaiting] = useState(true);
  // Seconds since this pane opened. A spinner with no elapsed time gives a
  // visitor no way to tell "working" from "broken", and this wait is genuinely
  // open-ended -- it ends when they run the command, which might be in five
  // seconds or two minutes.
  const [elapsed, setElapsed] = useState(0);
  const poll = useRef(null);

  // The collector runs on the visitor's own machine, so it can't reference a file
  // path from this repo. Instead it fetches the script from the backend and runs
  // it in-memory (same pattern as most installer one-liners), then POSTs its
  // result back to wherever that backend actually lives — localhost only in dev.
  const apiOrigin = import.meta.env.VITE_API_BASE || "http://localhost:8000";
  // The instruction has to match the machine the visitor is sitting at. Handing a
  // Mac user a PowerShell line reads as "this product is broken" rather than
  // "wrong command", and phones are told the truth instead of given something
  // that cannot work. See platform.js.
  const [platform] = useState(detectPlatform);
  const [showAllPlatforms, setShowAllPlatforms] = useState(false);
  const plat = deepScanCommand(platform, apiOrigin, token);
  const command = plat.command || "";
  const isWin = platform === PLATFORM.windows;

  // The SHA-256 of the collector served right now, so the downloadable .bat can
  // PIN it and refuse to run a tampered/intercepted script. Fetched up front (on
  // Windows) so the primary download is ready without a click.
  const [collectorHash, setCollectorHash] = useState(null);
  useEffect(() => {
    if (!isWin) return undefined;
    let alive = true;
    api.collectorSource("collector.ps1").then(async (src) => {
      try {
        const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(src));
        const h = [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, "0")).join("");
        if (alive) setCollectorHash(h.toUpperCase());   // Get-FileHash is uppercase
      } catch { /* insecure origin: no subtle.digest -- .bat still runs, unpinned */ }
    }).catch(() => {});
    return () => { alive = false; };
  }, [isWin]);

  // A double-clickable wrapper: no pasting a piped command into a shell, and a
  // file the reader can open in Notepad first. When the hash is known it verifies
  // the collector before running -- practicing the product's own "verify, don't
  // trust" pitch instead of asking for an irm|iex leap of faith.
  function buildBat() {
    const url = `${apiOrigin}/api/collector.ps1`;
    const post = `${apiOrigin}/api/deep-scan`;
    const pin = collectorHash || "";
    const verify = pin
      ? `$h=(Get-FileHash $t -Algorithm SHA256).Hash; if ($h -ne '${pin}') { Write-Host ''; `
        + `Write-Host 'SECURITY STOP: the downloaded collector does not match the pinned hash. Refusing to run it.' -ForegroundColor Red; `
        + `Remove-Item $t -Force; exit 1 }; Write-Host 'Collector verified. Reading this machine...' -ForegroundColor Green; `
      : "";
    const ps = `$ErrorActionPreference='Stop'; $t=Join-Path $env:TEMP 'afterlife_collector.ps1'; `
      + `Invoke-RestMethod '${url}' -OutFile $t; ${verify}`
      + `& $t -PostUrl '${post}' -Token '${token}'; Remove-Item $t -Force`;
    const lines = [
      "@echo off",
      "title Afterlife Deep Scan",
      "REM  Afterlife Deep Scan -- reads THIS machine's real hardware (processor, disk",
      "REM  health, battery wear, Windows 11 eligibility) and sends a SIGNED passport",
      "REM  back to your browser. Nothing is installed. Open this file in Notepad first",
      "REM  to see exactly what it runs.",
      pin && "REM  It refuses to run the collector unless its SHA-256 matches the pinned",
      pin && `REM  hash (${pin}) -- a tampered or intercepted script fails closed.`,
      "",
      `powershell -NoProfile -ExecutionPolicy Bypass -Command "${ps}"`,
      "",
      "echo.",
      "echo Done -- return to your browser; your verified passport appears there automatically.",
      "pause",
    ].filter((l) => l !== false && l != null);
    return lines.join("\r\n") + "\r\n";
  }

  function downloadBat() {
    const blob = new Blob([buildBat()], { type: "application/octet-stream" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "Afterlife Deep Scan.bat";
    a.click();
    URL.revokeObjectURL(a.href);
  }

  useEffect(() => {
    if (!waiting) return undefined;
    const t = setInterval(() => setElapsed((n) => n + 1), 1000);
    return () => clearInterval(t);
  }, [waiting]);

  useEffect(() => {
    poll.current = setInterval(async () => {
      try {
        const res = await api.pollDeep(token);
        if (res && !res.pending) {
          clearInterval(poll.current);
          setWaiting(false);
          setPassport(res);
          // Leave the marker now, while we know for a fact the collector just ran
          // on the machine in front of us -- that is the only moment this is
          // knowable. See deviceStore.js.
          markScanned(res.payload?.device_id);
          // QR generation is a nice-to-have, not load-bearing -- isolated so a
          // failure here only means "no QR," never silently skips
          // fetchAssessment() below too (that used to be the same try/catch,
          // and left the results pane stuck loading forever with no error).
          // Gzip-compressing the JSON before base64 shrinks a deep-scan
          // passport (win11 blockers, repairability, sub_scores,
          // persona_signals...) by roughly half, keeping every field intact
          // instead of dropping any of them to fit -- see b64.js.
          try {
            // issuer/validFrom are load-bearing, not decoration -- the passport is
            // signed over the whole W3C VC envelope (see passport.py's
            // _vc_envelope), not just `payload` alone, so leaving these two out
            // makes verify_payload() check the signature against the wrong bytes
            // and every legitimately-signed passport comes back "invalid."
            const signed = {
              payload: res.payload, signature: res.signature, issuer_pubkey: res.issuer_pubkey,
              issuer: res.issuer, validFrom: res.validFrom,
            };
            const data = b64encodeCompressed(signed);
            const url = `${window.location.origin}/?verify=${data}`;
            setQr(await (await import("qrcode")).default.toDataURL(url, {
              margin: 4, scale: 6, errorCorrectionLevel: "M",
              color: { dark: "#0e1518", light: "#ffffff" },
            }));
          } catch (qrErr) {
            console.warn("QR generation failed (passport still valid):", qrErr);
          }
          // Save to history only once the assessment (score/grade) is in hand,
          // so a saved row is always comparison-ready instead of bare specs.
          fetchAssessment(res.payload, null, res).then(setAssessment).catch(() => {});
        }
      } catch { /* keep polling */ }
    }, 1500);
    return () => clearInterval(poll.current);
  }, [token]);

  function copy() {
    navigator.clipboard.writeText(command);
    setCopied(true);
    setTimeout(() => setCopied(false), 1600);
  }

  function savePassport() {
    const blob = new Blob([JSON.stringify(passport, null, 2)], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `${passport.payload.device_id}.passport.json`;
    a.click();
  }

  function saveQr() {
    const a = document.createElement("a");
    a.href = qr;
    a.download = `${passport.payload.device_id}.qr.png`;
    a.click();
  }

  if (passport) {
    return (
      <div className="results-wrap">
        <div className="results-left" id="tour-passport">
          <PassportCard doc={passport} qr={qr}
            final={assessment?.blend ? { score: assessment.blend.combined_score, grade: assessment.blend.grade } : null} />
          <div className="passport-actions">
            <button className="cta" onClick={savePassport}>Save passport (JSON)</button>
            <button className="ghost" onClick={saveQr} disabled={!qr}>{qr ? "Save QR (PNG)" : "QR unavailable"}</button>
            <button className="ghost" onClick={onBack}>Start a new scan</button>
            <span className="note">
              Scan the QR with any phone camera to open the verifier, or save it and upload it there later.
            </span>
          </div>
        </div>
        <div className="results-right">
          {/* Rendered from the scan response directly rather than waiting on the
              assessment fetch -- this is measured hardware data, already present
              the moment the passport lands, so gating it behind the LLM narration
              would leave it blank for no reason. */}
          {/* The keep-or-replace argument leads, ahead of condition detail: it's
              the question someone actually came here to answer. */}
          {/* No token: the model-written explanation (Sprint 2, later) and the
              downloadable settings-changing hardening script (future scope) stay off. */}
          <MitigationReport mitigation={passport.mitigation} token={null} />
          <SecureBootAlert secureBoot={passport.secure_boot} />
          <ReliabilitySignals hardware={passport.hardware} />
          {assessment ? (
            <>
              <AssessmentDashboard data={assessment} payload={passport?.payload} />
            </>
          ) : (
            <div className="center"><span className="spinner" /> crunching real numbers, not vibes…</div>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="card pad-lg deep-wait">
      {plat.supported ? (
        <>
          <div className="deep-steps">
            <div className="deep-step"><span className="n">1</span> {isWin ? "Download the file below" : "Copy the command below"}</div>
            <div className="deep-step">
              <span className="n">2</span> {isWin ? "Double-click it (open it in Notepad first if you like)" : <>Paste it into {plat.shell} and press Enter</>}
            </div>
            <div className="deep-step"><span className="n">3</span> Your verified passport appears here automatically</div>
          </div>

          <div className="plat-badge">
            <span className="pill cyan">{plat.label} detected</span>
            <button className="inline-jump" onClick={() => setShowAllPlatforms((v) => !v)}>
              {showAllPlatforms ? "hide" : "scanning a different machine?"}
            </button>
          </div>

          {isWin ? (
            <>
              <div className="deep-download">
                <button className="cta" onClick={downloadBat} disabled={!collectorHash}>
                  {collectorHash ? "⬇ Download Afterlife Deep Scan.bat" : "preparing…"}
                </button>
                <p className="note">
                  A file you can open and read before running — no shell, no pasting an{" "}
                  <code>irm | iex</code> command. It downloads the collector and{" "}
                  {collectorHash
                    ? "refuses to run it unless its SHA-256 matches the hash pinned inside the file, so a tampered script fails closed."
                    : "runs it on your machine."}
                </p>
              </div>

              {/* The irm|iex one-liner is the honest fallback, not the front door:
                  power users get it, everyone else gets a file they can inspect. */}
              <details className="deep-advanced">
                <summary>Advanced — paste a one-line command instead</summary>
                <div className="cmd">
                  <code>{command}</code>
                  <button className="cta" onClick={copy}>{copied ? "Copied ✓" : "Copy"}</button>
                </div>
                <p className="note">{plat.note}</p>
              </details>
            </>
          ) : (
            <>
              <div className="cmd">
                <code>{command}</code>
                <button className="cta" onClick={copy}>{copied ? "Copied ✓" : "Copy"}</button>
              </div>
              <p className="note">{plat.note}</p>
            </>
          )}

          <CollectorSource platform={platform} apiOrigin={apiOrigin} />
        </>
      ) : (
        /* Phones, tablets and anything unrecognised. Saying plainly that a deep
           scan is impossible is more useful than offering a command that fails. */
        <div className="plat-unsupported">
          <span className="pill muted">{plat.label}</span>
          <p className="note" style={{ marginTop: "0.6rem" }}>{plat.note}</p>
          <button className="cta" style={{ marginTop: "0.8rem" }} onClick={onBack}>
            Run the instant scan instead
          </button>
          <button className="inline-jump" style={{ marginTop: "0.7rem", display: "block" }}
                  onClick={() => setShowAllPlatforms((v) => !v)}>
            {showAllPlatforms ? "hide" : "I'm scanning a computer, show me the commands"}
          </button>
        </div>
      )}

      {showAllPlatforms && (
        <div className="plat-all">
          {allCommands(apiOrigin, token).map((c) => (
            <div className="plat-one" key={c.label}>
              <div className="k-label" style={{ marginBottom: "0.35rem" }}>{c.label}</div>
              <code>{c.command}</code>
            </div>
          ))}
        </div>
      )}

      <div className="deep-status">
        {waiting && (
          <>
            {/* A checklist rather than a spinner. Every step is driven by state
                the browser actually knows -- nothing here advances on a timer,
                because a progress bar that guesses lies with specifics. */}
            <ScanProgress
              waiting={waiting}
              stalled={elapsed >= STALLED_AFTER}
              received={!!passport}
              signed={!!passport?.signature}
              assessed={!!assessment}
              elapsed={elapsed}
            />
            {elapsed >= STALLED_AFTER && (
              <ScanWait elapsed={elapsed} onInstant={onBack} />
            )}
          </>
        )}
      </div>

      {/* Partial success, itemised. A scan that reached everything but SMART is
          not a failure, but it is not the complete scan the passport used to
          claim either -- and when the gap is fixable by re-running elevated,
          that is worth one line. */}
      {!waiting && passport?.payload?.scan_coverage && (
        <ScanCoverage coverage={passport.payload.scan_coverage} />
      )}

      <p className="note">
        This runs right here on your computer and reads things a browser never can — your real
        processor, your disk's health, and your battery's true wear. It only sends the results
        straight back to this page, nothing else.
      </p>
      {platform === PLATFORM.windows && (
        <div className="deep-upgrade">
          <span className="pill amber">optional</span>
          <span className="note">
            Want your <b>Windows 11 upgrade eligibility</b> checked too? Run it as administrator —
            right-click <b>Afterlife Deep Scan.bat</b> (or PowerShell) → “Run as administrator”.
            Without admin you still get a full passport (processor,
            disk, <b>battery wear</b>, operating system) — you'll just see "needs admin" for the
            Windows 11 check.
          </span>
        </div>
      )}
      <button className="ghost" onClick={onBack}>Use instant scan instead</button>
    </div>
  );
}

// "No vibes, just verified data" has to apply to the collector itself. Asking
// someone to pipe a remote script into a shell is a real trust ask, so this lets
// them read the exact script that will run -- fetched from the same URL the
// command hits, so what they read is what runs -- see its source on GitHub, and
// independently verify its SHA-256. Lazy-loaded: it costs nothing until opened.
const REPO = "https://github.com/RuhinzGH/AfterLife/blob/main/collector";

function CollectorSource({ platform, apiOrigin }) {
  const isWin = platform === PLATFORM.windows;
  const file = isWin ? "collector.ps1" : "collector.sh";
  const repoFile = isWin ? "collect_device.ps1" : "collect_device.sh";
  const [state, setState] = useState({ loaded: false, loading: false, src: null, hash: null, err: null });

  async function load() {
    if (state.loaded || state.loading) return;
    setState((s) => ({ ...s, loading: true }));
    try {
      const src = await api.collectorSource(file);
      let hash = null;
      try {
        const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(src));
        hash = [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, "0")).join("");
      } catch { /* subtle unavailable on insecure origins; show script anyway */ }
      setState({ loaded: true, loading: false, src, hash, err: null });
    } catch (e) {
      setState({ loaded: true, loading: false, src: null, hash: null, err: e.message });
    }
  }

  const verifyCmd = isWin
    ? `irm ${apiOrigin}/api/collector.ps1 -OutFile collector.ps1; Get-FileHash collector.ps1 -Algorithm SHA256`
    : `curl -fsSL ${apiOrigin}/api/collector.sh | shasum -a 256`;

  return (
    <details className="collector-source" onToggle={(e) => e.target.open && load()}>
      <summary>See exactly what this runs — and verify it</summary>
      <div className="collector-source-body">
        <p className="note">
          The command fetches this script from <code>{apiOrigin}/api/{file}</code> and runs it. It
          reads hardware and posts the result back to this page — nothing else. Read it here, or on{" "}
          <a href={`${REPO}/${repoFile}`} target="_blank" rel="noopener noreferrer">GitHub</a>.
        </p>

        {state.loading && <div className="center"><span className="spinner" /> loading the script…</div>}
        {state.err && <p className="note bad">Couldn’t load it here — read it on GitHub instead: <a href={`${REPO}/${repoFile}`} target="_blank" rel="noopener noreferrer">{repoFile}</a>.</p>}

        {state.hash && (
          <div className="collector-hash">
            <div className="k-label">SHA-256 of the script served right now</div>
            <code className="hash">{state.hash}</code>
            <p className="note">
              Verify it yourself — run this and confirm the hash matches:
            </p>
            <code className="hash-verify">{verifyCmd}</code>
          </div>
        )}

        {state.src && <pre className="collector-code"><code>{state.src}</code></pre>}
      </div>
    </details>
  );
}

// The wait here is genuinely open-ended: it ends when the visitor runs the
// command, not when a server finishes something. So this does NOT invent stages
// and tick through them -- claiming "checking storage" while we have no idea
// what the collector is doing would be a lie told in a progress bar.
//
// What it does instead is give the wait a shape: how long it has been going, how
// long the scan itself usually takes once started, and -- past the point where
// something has clearly gone wrong -- says so rather than spinning forever.
const STALLED_AFTER = 75;

function ScanWait({ elapsed, onInstant }) {
  const mins = Math.floor(elapsed / 60);
  const secs = String(elapsed % 60).padStart(2, "0");
  const stalled = elapsed >= STALLED_AFTER;

  return (
    <div className="scan-wait">
      <div className="scan-wait-head">
        <span className="scan-pulse" aria-hidden="true">
          <i /><i /><i />
        </span>
        <span className="scan-wait-label">
          {stalled ? "still listening" : "listening for your scan"}
        </span>
        <span className="scan-wait-clock" aria-live="off">
          {mins}:{secs}
        </span>
      </div>

      <p className="note scan-wait-note">
        {stalled
          ? "Nothing has arrived yet. Usually one of three things: the command didn't actually run (check the terminal for an error and paste it back), a firewall or VPN is blocking the upload to Afterlife, or the scan is still finishing on a slow machine."
          : "Run the command above. The scan itself takes about twenty seconds once it starts, and the results land here on their own."}
      </p>

      {stalled && onInstant && (
        <div className="scan-wait-actions">
          <button className="ghost sm" onClick={onInstant}>Try the instant scan instead →</button>
        </div>
      )}
    </div>
  );
}
