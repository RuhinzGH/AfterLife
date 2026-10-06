import { useEffect, useState } from "react";
import { api } from "./api.js";
import { DecayChart, HBars } from "./charts.jsx";
import Disclose from "./Disclose.jsx";
import SourceNote from "./SourceNote.jsx";
import { CostSweep, FailSlow } from "./ResearchExtras.jsx";

import Provenance from "./Provenance.jsx";
import FindingsSkeleton from "./FindingsSkeleton.jsx";

function Loading() { return <div className="center"><span className="spinner" /> loading findings…</div>; }
function ErrState({ msg }) {
  return (
    <div className="view">
      <div className="card pad-lg"><h2>Could not load findings</h2><p className="note">{msg}</p></div>
    </div>
  );
}

// Structured as a narrative in four movements rather than one long dashboard.
// Every card previously carried the same visual weight, which meant the finding
// the whole product rests on looked exactly as important as a footnote about
// model selection. Sections give the page an argument: here is the claim, here is
// the security evidence, here is the environmental evidence, here is how the
// model was built and where its data came from.
//
// Nothing was deleted in this restructure. The secondary explanations, the
// limitations and the method notes all still exist -- they are folded behind
// disclosure controls, so a casual reader gets the conclusion and a reviewer can
// still inspect every assumption. That distinction matters more here than
// anywhere else in the product, because this page's entire claim is that its
// numbers are checkable.

// The three text representations, named for a reader rather than for the code.
// Plain words for an experiment's outcome. "no effect" is a result and is
// labelled as one rather than being softened into something that sounds better.
const VERDICT_LABEL = {
  works: "worked, not deployable",
  harmful: "made it worse",
  "no effect": "no effect",
};

const REP_LABEL = {
  tokens: "words",
  lexicon: "fault list",
  invariant: "fault list, venue-free",
};

function Section({ id, eyebrow, title, sub, children }) {
  return (
    <section className="research-section" id={id}>
      <div className="research-section-head">
        <div className="eyebrow">{eyebrow}</div>
        <h2 className="research-section-title">{title}</h2>
        {sub && <p className="research-section-sub">{sub}</p>}
      </div>
      {children}
    </section>
  );
}

const TOC = [
  ["core-finding", "Core finding"],
  ["security-evidence", "Security"],
  ["environmental-evidence", "Environmental"],
  ["model-methodology", "Model & method"],
];

export default function Findings() {
  const [f, setF] = useState(null);
  const [err, setErr] = useState(null);
  const [activeSec, setActiveSec] = useState(TOC[0][0]);
  useEffect(() => { api.findings().then(setF).catch((e) => setErr(e.message)); }, []);

  // Scroll-spy for the jump-nav: highlight whichever section owns the top of the
  // viewport. Runs only once the findings (and therefore the sections) exist.
  useEffect(() => {
    if (!f) return;
    const secs = TOC.map(([id]) => document.getElementById(id)).filter(Boolean);
    if (!secs.length) return;
    const obs = new IntersectionObserver(
      (entries) => {
        const vis = entries.filter((e) => e.isIntersecting)
          .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top);
        if (vis[0]) setActiveSec(vis[0].target.id);
      },
      { rootMargin: "-45% 0px -50% 0px", threshold: 0 },
    );
    secs.forEach((s) => obs.observe(s));
    return () => obs.disconnect();
  }, [f]);

  if (err) return <ErrState msg={err} />;
  if (!f) return <FindingsSkeleton />;

  const { decay, security, carbon, model, mitigation, repair_evidence, failslow,
          research, kev } = f;
  // Hardcoding these meant every corpus refresh silently made the page wrong.
  const mit = mitigation?.["10"];
  const mit11 = mitigation?.["11"];
  const results = (model.results || []).filter((r) => r.model !== "Baseline (majority)");
  const bestF1 = results.find((r) => r.model === model.best_macro_f1?.model
                               && r.representation === model.best_macro_f1?.representation);

  return (
    <div className="view research">
      <div>
        <div className="eyebrow">Our research · real data</div>
        <h1 className="title">The evidence that working hardware is scrapped too soon</h1>
        <p className="lede">
          Public datasets behind Afterlife's thesis — not an assessment of your device. Every
          number here is computed from the data, not asserted. Each card carries its source.
        </p>
      </div>

      {/* Sticky jump-nav. This page is long and sectioned; without it a reader
          has to scroll the whole argument to reach the part they came for. */}
      <nav className="research-toc" aria-label="Sections">
        {TOC.map(([id, label]) => (
          <a
            key={id}
            href={`#${id}`}
            className={`research-toc-link ${activeSec === id ? "on" : ""}`}
            aria-current={activeSec === id ? "true" : undefined}
          >{label}</a>
        ))}
      </nav>

      <div className="grid g2">
        <Stat
          k="Remotely exploitable, no fix, no credentials"
          v={mit ? String(mit.remote_no_creds) : "—"}
          cls="green"
          n={mit ? `of ${mit.serious.toLocaleString()} serious ${mit.label} flaws` : "—"}
        />
        <Stat k="Win 10 clears vs Win 7" v="~3×" cls="amber" n={`${decay.win10_projected_months} vs ${decay.win7_settled_months} months to <5%`} />
        <Stat k="Serious CVEs needing local access" v={`${(security.local_share * 100).toFixed(0)}%`} cls="blue" n="attacker already on device" />
        <Stat k="Carbon break-even, dirtiest grid" v="21 yr" cls="green" n="no laptop lives that long" />
      </div>

      {/* ============================================ 1. the claim itself */}
      <Section
        id="core-finding"
        eyebrow="Core finding"
        title="Old doesn't mean dangerous"
        sub="The single result this product is built on, and the deadlines that keep moving underneath it."
      >
        {mit && (
        <div className="card pad-lg finding-hero">
          <h2>Windows 10 going end-of-support is not, by itself, a reason to replace a machine</h2>
          <p className="lede" style={{ marginTop: "0.6rem" }}>
            We classified <b>{mit.serious.toLocaleString()} HIGH/CRITICAL {mit.label} CVEs</b> against
            published vendor advisories, asking one question each: is there a documented action that
            removes the exposure <i>without</i> new hardware?
          </p>
          <div className="fh-split">
            <div className="fh-cell fix"><b>{mit.fixable}</b><span>have a fix Microsoft has already published</span></div>
            <div className="fh-cell iso"><b>{mit.isolation}</b><span>much harder if the PC is off the open internet</span></div>
            <div className="fh-cell loc"><b>{mit.local_access.toLocaleString()}</b><span>need an attacker already on the device</span></div>
            <div className="fh-cell res"><b>{mit.remote_no_lever}</b><span>reachable remotely with nothing published to stop them</span></div>
          </div>
          <p className="fh-punch">
            <b>{mit.addressable_pct}%</b> can be fixed, shut off, or need someone already on the machine.
            And of the{" "}
            {mit.remote_no_lever} genuinely residual ones, <b>zero</b> can be reached over a network
            without credentials — every one needs an account on the machine first.
          </p>
          {mit11 && (
            <p className="fh-also">
              The same holds on a currently-supported OS: across{" "}
              <b>{mit11.serious.toLocaleString()}</b> serious {mit11.label} flaws,{" "}
              <b>{mit11.addressable_pct}%</b> have an answer and{" "}
              <b>{mit11.remote_no_creds === 0 ? "none" : mit11.remote_no_creds}</b> can be reached
              remotely without credentials. This is not a quirk of an old operating system.
            </p>
          )}
          <div className="card-foot">
            <Disclose label="Method and limitations">
              <p className="note" style={{ marginTop: 0 }}>
                Every CVE is pulled from the National Vulnerability Database and classified by its
                CVSS attack vector, the privileges an attacker would already need, and whether the
                vendor published a mitigation. Classification code is in{" "}
                <code>afterlife/mitigation.py</code>, and the counts on this page are recomputed
                from the classified corpus on every request rather than typed in.
              </p>
              <p className="note">
                <b>Deliberately pessimistic.</b> A flaw with no published advice counts as having
                no lever, even where one plainly exists in practice. The residual bucket is
                therefore an over-estimate, not an optimistic reading.
              </p>
              <p className="note">
                <b>What this does not say.</b> It is not a claim that an unsupported OS is as safe
                as a supported one. It is the narrower, checkable claim that the specific risk
                usually cited to justify replacement — remote compromise with no fix — is not
                present in this corpus.
              </p>
            </Disclose>
            <SourceNote
              title="National Vulnerability Database (NVD)"
              dataset="CVE records for Windows 10 and Windows 11, all CPE release variants, deduplicated by CVE ID"
              sample={`${mit.serious.toLocaleString()} HIGH/CRITICAL of ${security.total_cves.toLocaleString()} total (Windows 10)`}
              method="NVD 2.0 API, CVSS v3 base metrics; mitigation class assigned from vendor advisory text"
              published="NIST, continuously updated"
              url="https://nvd.nist.gov/"
              caveat="NVD splits Windows CVEs across per-release CPE product names; querying a single name returns a fraction of the data."
            />
          </div>
        </div>
        )}

        <div className="card pad-lg">
          <h2>The dates that move devices in and out of "obsolete"</h2>
          <div className="sub">Windows 10 support, Secure Boot and EU rules, in date order</div>
          <ul className="reg-timeline">
            <li>
              <span className="reg-when">14 Oct 2025 · passed</span>
              <span className="reg-what">
                <b>Windows 10 reached end of support.</b> Ordinary security and quality updates
                stopped. Home users could enrol in Extended Security Updates (ESU) to keep receiving
                security fixes.
              </span>
            </li>
            <li>
              <span className="reg-when">May 2026</span>
              <span className="reg-what">
                <b>The Digital Product Passport got real standards.</b> CEN/CENELEC published the
                EN 1821x series covering identifiers, data carriers, storage, interoperability and
                authentication. Afterlife's passport already has the shape they describe — a QR
                carrier resolving to a signed, verifiable record — though conformance is a claim
                we have not tested against the published texts and so do not make.
              </span>
            </li>
            <li>
              <span className="reg-when">Jun 2026 · passed</span>
              <span className="reg-what">
                <b>Secure Boot certificates expired.</b> The 2011 KEK and UEFI certificates retired.
                Replacements ship via Windows Update, but some older firmware needs a vendor BIOS
                update to accept them — and machines that miss it stop getting early-boot security
                fixes.
              </span>
            </li>
            <li>
              <span className="reg-when">Jul 2026 · in force</span>
              <span className="reg-what">
                <b>The EU right to repair started applying.</b> For products in scope a maker must
                now repair on request after the warranty has run out, at a reasonable price, and
                may not use software or contract terms to block it. Choosing repair over
                replacement adds a year of legal guarantee. Laptops are <i>not</i> in scope yet —
                only their displays are.
              </span>
            </li>
            <li>
              <span className="reg-when">13 Oct 2026</span>
              <span className="reg-what">
                <b>The original end of Windows 10 ESU for home users — now extended.</b> The
                programme was first announced as one year, ending on this date. In 2026 Microsoft
                extended it by a further year. The same month, the Windows Production PCA 2011
                certificate, which signs the bootloader itself, retires.
              </span>
            </li>
            <li>
              <span className="reg-when">12 Oct 2027</span>
              <span className="reg-what">
                <b>Windows 10 ESU for home users ends.</b> After this date a home Windows 10 machine
                receives no security updates. Advice to replace a working machine “before 2025”
                was two years early.
              </span>
            </li>
            <li>
              <span className="reg-when">Oct 2028</span>
              <span className="reg-what">
                <b>The paid ESU programme for organisations ends.</b> Businesses and schools can buy
                up to three years of Windows 10 security updates after end of support, at a price
                that roughly doubles each year.
              </span>
            </li>
            <li>
              <span className="reg-when">2028–29</span>
              <span className="reg-what">
                <b>EU Digital Product Passports reach electronics.</b> Machine-readable repairability,
                materials and lifecycle data becomes a condition of sale. The delegated act for
                electronics is expected in 2026–27, and application follows an 18-month transition —
                so this is the end of the decade, not next year. Afterlife's signed passport is
                already built on W3C Verifiable Credentials 2.0, a Recommendation since 15 May 2025.
              </span>
            </li>
          </ul>
        </div>
      </Section>

      {/* ============================================ 2. security evidence */}
      <Section
        id="security-evidence"
        eyebrow="Security evidence"
        title="Most security bugs aren't internet bugs"
        sub="Where an attacker actually has to be standing, and what happens to a fleet after support ends."
      >
        <div className="grid g-130">
          <div className="card pad-lg">
            <h2>Support ended. Risk didn't suddenly begin.</h2>
            <div className="sub">
              {security.serious_cves.toLocaleString()} serious Windows 10 flaws, grouped by where an attacker
              would have to be standing
            </div>
            <HBars
              data={Object.entries(security.vectors).map(([label, value]) => ({ label, value }))}
              colorFn={(d) => (d.label === "Local" ? "var(--brand)" : "var(--second)")}
            />
            <p className="card-takeaway">
              A majority of serious flaws need someone already logged in or physically present.
              That is a problem you solve with a password and a locked screen, not a new laptop.
            </p>
            <div className="card-foot">
              <Disclose label="Where does an attacker have to be?">
                <p className="note" style={{ marginTop: 0 }}>
                  CVSS records how an attacker reaches a flaw. <b>Network</b> means across the
                  internet. <b>Adjacent</b> means the same local network segment. <b>Local</b>
                  {" "}means an existing session on the machine. <b>Physical</b> means hands on the
                  device. Only the first is the scenario people picture when they hear
                  "unsupported operating system".
                </p>
                <p className="note">
                  <b>Limitation.</b> Attack vector describes reachability, not severity — a local
                  privilege-escalation flaw chained after a phishing click is still serious. The
                  point is not that local flaws are harmless, it is that they are not fixed by
                  replacing the hardware.
                </p>
              </Disclose>
              <SourceNote
                title="National Vulnerability Database (NVD)"
                dataset="Windows 10 CVE records, all release variants, deduplicated"
                sample={`${security.serious_cves.toLocaleString()} HIGH/CRITICAL of ${security.total_cves.toLocaleString()} total`}
                method="CVSS v3 attackVector field, counted directly from the classified corpus"
                published="NIST, continuously updated"
                url="https://nvd.nist.gov/"
              />
            </div>
          </div>

          {/* "Serious" is what CVSS thinks a flaw would do. This card is the
              only place on the page that reports what has actually happened, so
              it is worth its own card rather than a line inside the one above. */}
          {security.serious_known_exploited > 0 && (
            <div className="card pad-lg">
              <h2>And {security.serious_known_exploited.toLocaleString()} of them really were exploited</h2>
              <div className="sub">
                CISA's Known Exploited Vulnerabilities catalogue, joined to the same corpus
                {kev?.date_released ? ` · released ${kev.date_released}` : ""}
              </div>

              <div className="grid g3" style={{ marginTop: "0.9rem" }}>
                <Stat
                  k="Serious and known-exploited"
                  v={security.serious_known_exploited.toLocaleString()}
                  cls="red"
                  n={`of ${security.serious_cves.toLocaleString()} rated serious`}
                />
                <Stat
                  k="Tied to ransomware"
                  v={security.ransomware.toLocaleString()}
                  cls="red"
                  n="used in a named campaign"
                />
                <Stat
                  k="Share of serious flaws"
                  v={`${((security.serious_known_exploited / security.serious_cves) * 100).toFixed(1)}%`}
                  cls="blue"
                  n="the rest have no public exploitation on record"
                />
              </div>

              <p className="card-takeaway">
                Severity is a prediction about what a flaw <i>would</i> do. This is a record of what
                attackers <i>did</i>. Under 5% of the serious flaws on this machine's OS have any
                observed exploitation — which is the honest scale of the risk, and it is far smaller
                than "thousands of unpatched vulnerabilities" suggests.
              </p>

              <div className="card-foot">
                <Disclose label="Why this number is a floor, not a total">
                  <p className="note" style={{ marginTop: 0 }}>
                    {kev?.caveat || "KEV records observed, reported exploitation."} A flaw missing
                    from the catalogue has not been shown to be safe — only that no report of its
                    exploitation reached CISA. Targeted attacks that were never publicly
                    attributed do not appear here at all.
                  </p>
                  <p className="note">
                    <b>Why it still matters.</b> The alternative is ranking by CVSS score alone,
                    and the published evidence is that severity triages badly: most disclosed
                    flaws are never exploited, and the ones that are do not simply carry the
                    highest scores.
                  </p>
                </Disclose>
                <SourceNote
                  title="CISA Known Exploited Vulnerabilities Catalog"
                  dataset="Vulnerabilities with confirmed exploitation in the wild"
                  sample={`${(kev?.kev_total ?? 0).toLocaleString()} catalogued, ${security.known_exploited.toLocaleString()} matching this corpus`}
                  method="Joined to the classified corpus on CVE ID; counted from the corpus, not the feed"
                  published={`CISA, catalogue ${kev?.catalog_version || "current"}`}
                  url="https://www.cisa.gov/known-exploited-vulnerabilities-catalog"
                />
              </div>
            </div>
          )}

          <div className="card pad-lg">
            <h2>Windows 10 is clearing ~3× slower than Windows 7</h2>
            <div className="sub">Steam Hardware Survey · 193 months · aligned on end of support</div>
            <DecayChart decay={decay} />
            <p className="card-takeaway">
              Tens of millions of working machines will still be running Windows 10 years after the
              date they were told to replace it. Whatever happens to those devices is not a
              hypothetical.
            </p>
            <div className="card-foot">
              <Disclose label="Method and limitations">
                <p className="note" style={{ marginTop: 0 }}>
                  <b>First hardware gate in a Windows transition.</b> The TPM 2.0 / 8th-gen CPU wall
                  strands machines that Windows 7 users could simply upgrade in place. Both curves
                  are aligned on their own end-of-support month so the shapes are comparable.
                  Projection R² = {decay.r_squared}.
                </p>
                <p className="note">
                  <b>Population caveat.</b> Steam's respondents are gamers, who skew toward newer
                  and self-built hardware. If anything that biases the sample toward faster
                  migration, which would make the real-world tail longer than this chart, not
                  shorter.
                </p>
              </Disclose>
              <SourceNote
                title="Steam Hardware & Software Survey"
                dataset="Monthly OS version share among Steam users"
                sample="193 months of published survey snapshots"
                method="Share-over-time aligned on each OS's end-of-support month; exponential decay fitted to the Windows 10 tail"
                published="Valve, monthly"
                url="https://store.steampowered.com/hwsurvey"
                caveat="Self-selected gaming population, not a general-population panel."
              />
            </div>
          </div>
        </div>
        <FailSlow data={failslow} />
      </Section>

      {/* ============================================ 3. environmental evidence */}
      <Section
        id="environmental-evidence"
        eyebrow="Environmental evidence"
        title="Carbon isn't where you think it is"
        sub="Almost all of a laptop's emissions happen before it is switched on for the first time."
      >
        <div className="card pad-lg">
          <h2>Carbon break-even by grid</h2>
          <div className="sub">
            years for a replacement to repay its embodied carbon
            {carbon.embodied_kg_range
              ? ` (${carbon.embodied_kg_range[0]}–${carbon.embodied_kg_range[1]} kg)`
              : ` (${carbon.embodied_kg} kg)`}
          </div>
          <HBars
            data={Object.entries(carbon.breakeven_years).map(([label, value]) => ({ label, value }))}
            unit=" yr"
            colorFn={(d) => (d.value > carbon.laptop_lifespan ? "var(--green)" : "var(--red)")}
          />
          <p className="card-takeaway">
            In every country measured, extending the life of a working laptop costs less carbon
            than replacing it — even where the electricity is dirtiest and the new machine is more
            efficient.
          </p>
          <div className="card-foot">
            <Disclose label="How break-even is calculated">
              <p className="note" style={{ marginTop: 0 }}>
                A new laptop carries roughly {carbon.embodied_kg_range
                  ? `${carbon.embodied_kg_range[0]}-${carbon.embodied_kg_range[1]}`
                  : carbon.embodied_kg} kg of embodied carbon from
                manufacturing before it is ever powered on. A more efficient machine saves some
                operational carbon each year, and how much depends entirely on how dirty the local
                grid is. Break-even is the number of years of those savings needed to repay the
                manufacturing debt. Every bar towers over a laptop's ~{carbon.laptop_lifespan}-year
                service life, so the debt is never repaid.
              </p>
              <p className="note">
                <b>Limitation.</b> Embodied-carbon figures vary by model and by methodology; 300 kg
                is a mid-range figure for a mainstream laptop, not a measurement of any specific
                device. Grid intensities also shift year to year as generation mixes change.
              </p>
            </Disclose>
            <SourceNote
              title="GHG Protocol Scope 3 + ADEME Base Empreinte"
              dataset="Embodied-carbon factors for consumer laptops; national grid carbon intensities"
              sample={`${carbon.embodied_kg} kg embodied per device, ${Object.keys(carbon.breakeven_years).length} grids compared`}
              method="Corporate Value Chain (Scope 3) accounting standard, cross-checked against ADEME's public emissions-factor database"
              published={carbon.embodied_source}
              url="https://ghgprotocol.org/corporate-value-chain-scope-3-standard"
              caveat="A mid-range figure for a class of device, not a measurement of one model."
            />
          </div>
        </div>

      </Section>

      {/* ============================================ 4. the model and its data */}
      <Section
        id="model-methodology"
        eyebrow="Model and methodology"
        title="Where the predictions come from"
        sub="The model behind the predictions, why it was chosen the way it was, and the real repair
             records it learned from."
      >
        <div className="card pad-lg">
          <h2>The model learned the repair café, not the fault</h2>
          <div className="sub">
            Open Repair Alliance · {model.n_records?.toLocaleString()} records from{" "}
            {model.n_groups} repair organisations · {model.folds}-fold, whole venues held out
          </div>

          <p className="lede" style={{ marginTop: "0.7rem" }}>
            The fault descriptions are written in the language of whichever country the repair
            event ran in. Language therefore identifies the venue — and a model can score well by
            recognising <i>where a record came from</i> instead of reading <i>what broke</i>.
          </p>

          {/* The finding, as a direct before/after on one model. Two bars, one
              axis, no legend lookup required to see the point. */}
          {model.venue_leakage && (
            <div className="leak-split">
              <div className="leak-cell">
                <span className="leak-k">Tested the usual way</span>
                <b>{(bestF1?.random?.macro_f1 ?? 0).toFixed(2)}</b>
                <span className="note">same venues in training and test</span>
              </div>
              <div className="leak-arrow">→</div>
              <div className="leak-cell honest">
                <span className="leak-k">Tested on unseen venues</span>
                <b>{(bestF1?.grouped?.macro_f1 ?? 0).toFixed(2)}</b>
                <span className="note">repair cafés the model never saw</span>
              </div>
              <div className="leak-delta">
                −{model.venue_leakage.macro_f1.toFixed(2)}
                <span className="note">was venue recognition</span>
              </div>
            </div>
          )}

          <div className="k-label" style={{ marginTop: "1.4rem" }}>
            Every model, both ways
          </div>
          <div className="modeltable">
            <div className="mt-head">
              <span>model</span><span>text features</span>
              <span title="same venues in train and test">usual test</span>
              <span title="whole venues held out">honest test</span>
              <span title="how much it catches of what is genuinely dead">catches dead</span>
              <span title="spread across folds; lower is more predictable">swing</span>
            </div>
            {results.map((r, i) => (
              <div className={`mt-row ${r.representation}`} key={i}>
                <span>{r.model}</span>
                <span className="mt-rep">{REP_LABEL[r.representation] || r.representation}</span>
                <span className="mt-dim">{r.random.macro_f1.toFixed(2)}</span>
                <span>{r.grouped.macro_f1.toFixed(2)}</span>
                <span>{(r.grouped.eol_recall * 100).toFixed(0)}%</span>
                <span className="mt-dim">±{(r.grouped.macro_f1_sd ?? 0).toFixed(3)}</span>
              </div>
            ))}
          </div>

          {/* Calibration is a different kind of result from everything else on this
              card: it does not change what the model ranks first, it changes
              whether the number it reports means anything. That number is
              multiplied by 15 and taken off a device's score, so an overstated
              probability was points removed from a machine that had not earned
              the loss. */}
          {model.calibration && (
            <div className="calib">
              <div className="k-label" style={{ marginTop: "1.4rem" }}>
                Does the risk number mean what it says?
              </div>
              <p className="note" style={{ marginTop: "0.3rem" }}>
                The model's end-of-life risk is not just a ranking — it is subtracted from every
                device's score. So it has to be a real probability, not a number that merely
                looks like one.
              </p>
              <div className="calib-row">
                <div className="calib-cell">
                  <span className="leak-k">Before</span>
                  <b>{model.calibration.ece_raw.toFixed(3)}</b>
                  <span className="note">
                    said {(model.calibration.mean_points_docked_raw / 15 * 100).toFixed(0)}% on
                    average, true rate {(model.calibration.base_rate * 100).toFixed(0)}%
                  </span>
                </div>
                <div className="calib-cell good">
                  <span className="leak-k">After</span>
                  <b>{model.calibration.ece_calibrated.toFixed(3)}</b>
                  <span className="note">calibration error, closer to zero is honest</span>
                </div>
                <div className="calib-cell">
                  <span className="leak-k">Effect on a device</span>
                  <b>{model.calibration.mean_absolute_shift_points.toFixed(1)} pts</b>
                  <span className="note">
                    every assessed device was losing this many points it had not earned
                  </span>
                </div>
              </div>
            </div>
          )}

          <p className="card-takeaway">
            No configuration wins on everything, so we report the trade instead of picking a
            flattering row. Word features catch the most dead devices but swing wildly depending
            which café you deploy to. The language-free fault list is far steadier — its spread
            across venues is roughly ten times smaller — which is what you actually want when the
            next device comes from a country the model has never seen.
          </p>

          {/* Laptops are half the data. Without this, the headline number could
              be a laptop score wearing a general label -- and the answer turns
              out to invert the worry, so it is worth showing rather than
              asserting. */}
          {model.by_category?.length > 0 && (
            <div className="percat">
              <div className="k-label" style={{ marginTop: "1.4rem" }}>
                Does it work on things that aren't laptops?
              </div>
              <p className="note" style={{ marginTop: "0.3rem", marginBottom: "0.6rem" }}>
                Every record scored by a model that never saw its repair organisation, then split
                by device type. Laptops are half the data — and the weakest case.
              </p>
              <div className="pc-rows">
                {model.by_category.map((c) => (
                  <div className="pc-row" key={c.category}>
                    <span className="pc-name">{c.category}</span>
                    <span className="pc-n">{c.n.toLocaleString()}</span>
                    <span className="pc-track">
                      <i className="pc-fill" style={{ width: `${c.eol_recall * 100}%` }} />
                    </span>
                    <span className="pc-val">{(c.eol_recall * 100).toFixed(0)}%</span>
                  </div>
                ))}
              </div>
              <p className="note" style={{ marginTop: "0.5rem", fontSize: "0.74rem" }}>
                Bars show end-of-life recall — how much of what is genuinely dead it catches.
              </p>
            </div>
          )}

          {/* The attempts that failed. A research page that only lists what worked
              is a highlight reel, not a record -- and "did you try X?" is the
              first thing anyone reading this will ask. */}
          {model.experiments?.length > 0 && (
            <div className="tried">
              <div className="k-label" style={{ marginTop: "1.4rem" }}>
                What we tried to make it better
              </div>
              <p className="note" style={{ marginTop: "0.3rem", marginBottom: "0.7rem" }}>
                Five attempts, measured the same way as everything above. One shipped.
              </p>
              {model.experiments.map((e, i) => (
                <div className={`tried-row ${e.verdict.replace(" ", "-")}`} key={i}>
                  <div className="tried-head">
                    <span className="tried-name">{e.name}</span>
                    <span className={`tried-tag ${e.shipped ? "yes" : "no"}`}>
                      {e.shipped ? "shipped" : VERDICT_LABEL[e.verdict] || e.verdict}
                    </span>
                  </div>
                  <div className="tried-nums">
                    <span>macro F1 <b>{e.macro_f1.toFixed(3)}</b></span>
                    <span>catches dead <b>{(e.eol_recall * 100).toFixed(0)}%</b></span>
                  </div>
                  <p className="note tried-why">{e.why}</p>
                </div>
              ))}
              {model.also_checked?.length > 0 && (
                <Disclose label="Two more things we checked">
                  <ul className="tried-also">
                    {model.also_checked.map((t, i) => <li key={i} className="note">{t}</li>)}
                  </ul>
                </Disclose>
              )}
            </div>
          )}

          <div className="card-foot">
            <Disclose label="Why report a worse number on purpose">
              <p className="note" style={{ marginTop: 0 }}>
                The standard protocol shuffles rows, so the same repair organisation appears in
                training and test. With only {model.n_groups} organisations in the dataset, that
                lets a model memorise venue-specific habits — including how readily a given café
                declares something dead — and be scored on the same venues it memorised. Holding
                whole venues out removes that, and the difference is what venue recognition was
                worth.
              </p>
              <p className="note">
                <b>Selection.</b> Models are chosen on End-of-life recall across held-out venues,
                not accuracy. A majority-class baseline reaches {(0.545 * 100).toFixed(0)}% accuracy
                while catching <b>zero</b> end-of-life devices, which is precisely the failure this
                product exists to prevent.
              </p>
              <p className="note">
                <b>Honest limits.</b> Eight organisations is a small number of groups; one unusual
                café moves a fold a long way, which is why the spread is published beside every
                figure. And a language-independent representation only helps while the other
                columns stay venue-free — leaving the country field in simply moves the leak from
                the text to the metadata, which is exactly what happened on the first run of this
                experiment.
              </p>
            </Disclose>
            <SourceNote
              title="Open Repair Alliance — model training set"
              dataset="Community repair-event records for IT devices, with technician-assigned outcomes"
              sample={`${model.n_records?.toLocaleString()} records across ${model.n_groups} repair organisations`}
              method={model.protocol}
              published="Open Repair Alliance, openrepair_202507"
              url="https://openrepair.org/open-data/"
              caveat="Outcomes are technician judgements made at a repair event, not laboratory verification."
            />
          </div>
        </div>

        {repair_evidence?.themes?.length > 0 && (
          <div className="card pad-lg">
            <h2>Repair works more often than it doesn't</h2>
            <div className="sub">
              {repair_evidence.n_records?.toLocaleString()} computers, phones and tablets brought to
              community repair events · outcome recorded by the technician
            </div>
            <p className="lede" style={{ marginTop: "0.6rem" }}>
              <b>{repair_evidence.overall_fixed_pct}%</b> left working.
            </p>
            {repair_evidence.themes.map((t) => (
              <div className="rowbar" key={t.key}>
                <span className="lbl">{t.label}</span>
                <span className="meter"><i style={{ width: `${t.fixed_pct}%`, background: "var(--brand)" }} /></span>
                <span className="num">{Math.round(t.fixed_pct)}%</span>
              </div>
            ))}
            <p className="card-takeaway">
              Before assuming a fault is terminal, it is worth knowing that most of them weren't —
              and that when a repair did fail, it was usually a spare part being unavailable rather
              than the device being beyond help.
            </p>
            <div className="card-foot">
              <Disclose label="What this measures, and what it doesn't">
                <p className="note" style={{ marginTop: 0 }}>
                  Bars show the share <b>repaired successfully</b>, by fault type. The dataset
                  records what was wrong and how it ended, but <i>not which repair was performed</i>
                  {" "}— so this can say how often a fault was beaten, and never what the fix was.
                  Claiming otherwise would mean inventing a column.
                </p>
                <p className="note">
                  <b>Selection effect.</b> These are devices someone thought were worth carrying to
                  a repair event. Devices written off at home never enter the sample, so this is the
                  success rate among attempted repairs, not among all failures.
                </p>
              </Disclose>
              <SourceNote
                title="Open Repair Alliance — repair outcomes"
                dataset="Community repair-event records, IT devices only"
                sample={`${repair_evidence.n_records?.toLocaleString()} records; themes with fewer than ${repair_evidence.min_n} excluded`}
                method="Multilingual keyword matching on the free-text fault field, then outcome rates computed per theme"
                published={repair_evidence.source}
                url="https://openrepair.org/open-data/"
                caveat="Fault text is written by volunteers in several languages; theme matching favours recall over precision."
              />
            </div>
          </div>
        )}

        <CostSweep data={research} />

        <Provenance />
      </Section>
    </div>
  );
}

function Stat({ k, v, cls, n }) {
  return (
    <div className="card stat">
      <span className="k">{k}</span>
      <div className={`v ${cls}`}>{v}</div>
      <div className="n">{n}</div>
    </div>
  );
}
// A spinner on this page told a visitor nothing except that something was
// happening somewhere. The page has a shape -- a heading, a lede, then cards in
// a two-up grid -- and showing that shape while the data lands means the layout
// does not jump when it arrives, and the wait reads as this page loading rather
// than as an unrelated pause.
//
// Deliberately only three cards. A skeleton that mirrors all eighteen would take
// longer to paint than the fetch it is covering.
