import { useEffect, useState } from "react";

// A one-word "Source" link under every chart that opens the provenance in full:
// what the dataset is, how big it is, how it was collected, when, and where to go
// and check it.
//
// The point is not decoration. This page's entire claim is that its numbers are
// computed from real public data rather than asserted, and that claim is only
// checkable if the reader can find the data. Putting the full citation inline
// under seven charts would bury the charts; putting it one click away costs a
// reader nothing and makes every figure auditable.
//
// Every field here is optional except `title`, because the sources genuinely
// differ -- a customs dataset has no sample size in the sense a survey does.

export default function SourceNote({ title, dataset, sample, method, published, url, caveat }) {
  const [open, setOpen] = useState(false);

  // Escape closes it. A modal you can only dismiss by finding the right button is
  // a trap, and this one can open over a long scrolled page.
  useEffect(() => {
    if (!open) return;
    const onKey = (e) => { if (e.key === "Escape") setOpen(false); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  const rows = [
    ["Dataset", dataset],
    ["Sample", sample],
    ["Method", method],
    ["Published", published],
  ].filter(([, v]) => v);

  return (
    <>
      <button className="source-link" onClick={() => setOpen(true)}>
        Source
      </button>

      {open && (
        <div className="source-backdrop" onClick={() => setOpen(false)} role="presentation">
          <div
            className="source-modal"
            role="dialog"
            aria-modal="true"
            aria-label={`Source: ${title}`}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="source-modal-head">
              <div className="k-label" style={{ marginBottom: 0 }}>Source</div>
              <button className="collapse-x" onClick={() => setOpen(false)} aria-label="Close">✕</button>
            </div>
            <h3 className="source-title">{title}</h3>
            <div className="source-rows">
              {rows.map(([k, v]) => (
                <div className="source-row" key={k}>
                  <span className="source-k">{k}</span>
                  <span className="source-v">{v}</span>
                </div>
              ))}
            </div>
            {caveat && <p className="source-caveat">{caveat}</p>}
            {url && (
              <a className="source-url" href={url} target="_blank" rel="noreferrer noopener">
                Open the source ↗
              </a>
            )}
          </div>
        </div>
      )}
    </>
  );
}
