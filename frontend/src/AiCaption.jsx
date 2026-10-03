// A quiet marker under every written summary. The whole credibility pitch rests
// on people always knowing which numbers are COMPUTED and how the words around
// them were produced, so the summary says plainly that it is assembled by fixed
// rules from the numbers on screen and cannot change any of them.
export default function AiCaption({ source }) {
  if (!source) return null;
  return (
    <p className="ai-caption is-fallback">
      <span className="ai-caption-mark" aria-hidden="true">▚</span>
      Deterministic summary — written from the computed numbers by fixed rules.
    </p>
  );
}
