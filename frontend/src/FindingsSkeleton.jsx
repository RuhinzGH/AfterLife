/**
 * Loading placeholder for the research view.
 *
 * Lives in its own module because both sides of a code-split boundary need it,
 * and neither of the obvious homes works. App.jsx uses it as the Suspense
 * fallback while the Findings chunk downloads, so it has to be in the main
 * bundle; Findings.jsx uses it again once mounted, while its own API call is in
 * flight. Defining it in Findings.jsx and importing it into App.jsx would drag
 * the whole lazy chunk back into the entry bundle and undo the split. Importing
 * it from App.jsx into Findings.jsx would make the two modules circular.
 *
 * It was previously defined only in App.jsx, which meant Findings.jsx referenced
 * a name that did not exist in its own scope -- a ReferenceError on every visit
 * to the research tab, thrown in the gap between mount and first response.
 */
export default function FindingsSkeleton() {
  return (
    <div className="view skel-wrap" aria-busy="true" aria-label="Loading findings">
      <div className="skel skel-eyebrow" />
      <div className="skel skel-title" />
      <div className="skel skel-lede" />
      <div className="grid g-130 skel-grid">
        {[0, 1, 2].map((i) => (
          <div className="card pad-lg skel-card" key={i} style={{ "--i": i }}>
            <div className="skel skel-h2" />
            <div className="skel skel-sub" />
            <div className="skel skel-chart" />
            <div className="skel skel-line" />
            <div className="skel skel-line short" />
          </div>
        ))}
      </div>
    </div>
  );
}
