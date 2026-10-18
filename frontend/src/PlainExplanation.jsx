import { useEffect, useState } from "react";
import { api } from "./api.js";

// "In plain words" (S2-08). Asked for after the result is on screen, so the page
// never waits for it. A language model words the already-computed result; the
// server rejects any reply containing a number that is not on this page
// (afterlife/explain.py) and returns the rule-based summary instead, with the
// reason. The card always says which of the two it is showing.

export default function PlainExplanation({ data, tier }) {
  const [res, setRes] = useState(null);

  useEffect(() => {
    let live = true;
    setRes(null);
    api.explain(data, tier).then((r) => live && setRes(r)).catch(() => live && setRes({ failed: true }));
    return () => { live = false; };
  }, [data, tier]);

  if (res?.failed) return null;                       // the rule-based summary below is still there
  const model = res && res.source !== "rule-based";

  return (
    <div className="dash-card plain-words">
      <div className="k-label">
        In plain words
        {res && <span className={`pill ${model ? "cyan" : "muted"}`}>{model ? "language model" : "rule-based"}</span>}
      </div>
      {!res ? (
        <p className="note"><span className="spinner" /> wording the result…</p>
      ) : (
        <>
          <p className="ai-summary">{res.text}</p>
          <p className="ai-caption">
            {model
              ? <>Worded by a {res.source} from the numbers on this page. It cannot change them: every
                  number in it was checked against the page before it was shown.</>
              : <>Showing the rule-based summary{res.reason ? ` (${res.reason})` : ""}.</>}
          </p>
        </>
      )}
    </div>
  );
}
