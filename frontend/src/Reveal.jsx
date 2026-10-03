import { useEffect, useRef, useState } from "react";

// Fades + slides a section in the moment it scrolls into view, instead of
// everything on a long results page being visible (and static) the instant
// it renders -- the same "content arrives as you scroll" feel real product
// pages use. Plain IntersectionObserver, no animation library: fires once
// per element, then disconnects, so scrolling back up/down never re-triggers
// or fights component state.
export default function Reveal({ children, delay = 0, className = "" }) {
  const ref = useRef(null);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const io = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setVisible(true);
          io.disconnect();
        }
      },
      { threshold: 0.15, rootMargin: "0px 0px -40px 0px" }
    );
    io.observe(el);
    return () => io.disconnect();
  }, []);

  return (
    <div ref={ref} className={`reveal ${visible ? "in" : ""} ${className}`} style={{ transitionDelay: `${delay}ms` }}>
      {children}
    </div>
  );
}
