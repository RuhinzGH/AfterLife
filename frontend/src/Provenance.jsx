import Disclose from "./Disclose.jsx";

// Two things a reviewer looks for and could not previously find in one place.
//
// The limitations were all present, but scattered across a dozen disclosures --
// good for someone reading a card, useless for someone auditing the work. The
// reproducibility mapping did not exist at all: every number here is computed,
// and nothing said by what.

const SCRIPTS = [
  ["The keep-or-replace finding", "scripts/build_cve_corpus.py", "afterlife/mitigation.py",
   "Pulls every Windows CVE from NVD across all release variants, deduplicates, and classifies each against published vendor advisories."],
  ["Windows 10 decay curve", "scripts/export_decay_series.py", "app_data/decay.json",
   "Steam Hardware Survey share over time, aligned on each OS's end-of-support month."],
  ["The classifier and its evaluation", "scripts/train_lifecycle.py", "app_data/lifecycle_metrics.json",
   "Grouped by data provider, three representations, both protocols, calibration and per-category validation."],
  ["What the wrong metric costs", "scripts/downstream_sim.py", "app_data/downstream_sim.json",
   "Runs both models over the same test set and compares decisions row by row."],
  ["Cross-validated comparison", "scripts/research_experiment.py", "app_data/research_results.json",
   "Five-fold CV and the cost-ratio sweep."],
  ["Disk failure model", "scripts/train_nvme_failure_model.py", "app_data/nvme_model_results.json",
   "692,195 drives, three feature variants including the deployable-only one."],
  ["Fail-slow analysis", "scripts/analyze_failslow.py", "app_data/failslow_results.json",
   "Share of drives running abnormally slow, by duration, SSD against HDD."],
  ["Repair outcomes by fault", "scripts/build_repair_evidence.py", "app_data/repair_evidence.json",
   "Multilingual fault themes matched against recorded outcomes."],
  ["Per-country repair data", "scripts/build_country_eol.py", "app_data/country_eol.json",
   "End-of-life rate, repair success and top faults per country."],
  ["Where e-waste moves", "scripts/build_ewaste_trade.py", "app_data/ewaste_trade.json",
   "UN Comtrade HS 8549, net export ratio per country."],
  ["Which flaws were really exploited", "scripts/enrich_cve_kev.py", "app_data/kev_summary.json",
   "CISA's Known Exploited Vulnerabilities catalogue joined to the CVE corpus on CVE ID."],
  ["Embodied carbon per device", "scripts/build_embodied_carbon.py", "app_data/embodied_carbon.json",
   "Boavizta's manufacturer LCA declarations, reduced to a per-class distribution and a per-model lookup."],
];

const LIMITS = [
  ["Eight data providers is a small number of groups",
   "Every grouped result on this page is averaged over four folds drawn from eight repair organisations. One unusual organisation moves a fold a long way, which is why the spread is published beside every figure rather than only the mean."],
  ["The classifier is weak, and honestly so",
   "Roughly 0.41 macro F1 on unseen venues. The task is predicting a repair outcome from one line of volunteer-written text in four languages, with age recorded for only a third of records, against labels that are a technician's judgement on the day. No model gets strong performance from that."],
  ["Labels are judgements, not measurements",
   "End-of-life rates range from 1.3% to 43.1% across venues. The same laptop plausibly gets labelled differently depending who saw it and what parts were in the box."],
  ["The repair data is self-selected",
   "These are devices someone thought were worth carrying to a repair event, in countries that run them. Rates describe attempted repairs, not all failures, and the country spread may reflect who turns up as much as how repairable devices are."],
  ["The CVE finding counts documented mitigations only",
   "A flaw with no published vendor advice counts as having no lever even where one plainly exists. The residual bucket is an over-estimate rather than an optimistic reading."],
  ["Carbon figures are manufacturers' own declarations",
   "The headline number is now the median of 452 published laptop LCAs rather than a range quoted from a methodology document, and a device we can identify gets its own model's figure. But these are numbers manufacturers publish about themselves, using methods that are neither uniform nor fully disclosed — sound for orders of magnitude and for comparing two models from one maker, unsound for comparing makers against each other. The downstream figures still exclude both the replacement's operational emissions and the scrapped unit's disposal."],
  ["Known-exploited counts are a floor, never a total",
   "A flaw absent from CISA's catalogue has not been shown to be safe — only that no report of its exploitation reached CISA. Targeted attacks that were never publicly attributed do not appear at all. The number is useful because it is evidence of what did happen, not proof of what didn't."],
  ["The disk findings come from datacentre fleets",
   "Alibaba's drives under Alibaba's workloads. The direction of the fail-slow result is more transferable than its rates; a laptop SSD is not this population."],
  ["The trade map counts declared waste only",
   "Electronics exported labelled as 'used goods for reuse' do not appear, and that is a large and deliberate blind spot in the source data rather than in this analysis."],
  ["Nothing here has been tested with users",
   "Every interface decision on this site is reasoned and none is validated against someone who did not build it."],
];

export default function Provenance() {
  return (
    <div className="card pad-lg">
      <h2>How to check any of this</h2>
      <div className="sub">
        every number on this page, and the script that produces it
      </div>

      <p className="lede" style={{ marginTop: "0.7rem" }}>
        Nothing here is typed in by hand. Each figure is written to an artifact by a script in the
        repository, and the page reads the artifact — which is what stops a refresh silently
        leaving the copy asserting something that is no longer true.
      </p>

      <Disclose label="Which script produces which number" open>
        <div className="prov-list">
          {SCRIPTS.map(([what, script, out, why]) => (
            <div className="prov-row" key={script}>
              <div className="prov-what">{what}</div>
              <code className="prov-script">{script}</code>
              <code className="prov-out">{out}</code>
              <p className="note prov-why">{why}</p>
            </div>
          ))}
        </div>
      </Disclose>

      <div className="k-label" style={{ marginTop: "1.6rem" }}>
        What this work cannot tell you
      </div>
      <p className="note" style={{ marginTop: "0.3rem", marginBottom: "0.7rem" }}>
        Collected in one place. Each of these appears beside the result it applies to as well —
        this is for anyone who would rather read them together.
      </p>
      <div className="limits">
        {LIMITS.map(([title, detail]) => (
          <div className="limit-row" key={title}>
            <b>{title}</b>
            <span className="note"> {detail}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
