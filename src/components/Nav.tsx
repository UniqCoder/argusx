import { useScrollProgress } from "@/lib/scroll-store";

const STATES = ["Network", "Bitcoin", "Ledger", "Multi-chain", "Investigation"];
const MARKS = [0, 0.2, 0.55, 0.78, 0.93];

export function Nav() {
  const p = useScrollProgress();
  const compact = p > 0.02;
  const active = MARKS.reduce((acc, m, i) => (p >= m ? i : acc), 0);

  const handleJump = (mark: number) => {
    const story = document.getElementById("story");
    if (!story) return;
    const totalScrollable = story.scrollHeight - window.innerHeight;
    window.scrollTo({
      top: Math.max(0, mark * totalScrollable),
      behavior: "smooth",
    });
  };

  return (
    <header className={`nav ${compact ? "nav--compact" : ""}`}>
      <a
        href="#top"
        className="nav__brand"
        aria-label="Argus — back to top"
        onClick={(e) => {
          e.preventDefault();
          window.scrollTo({ top: 0, behavior: "smooth" });
        }}
      >
        <span className="nav__mark" aria-hidden="true" />
        ARGUS
      </a>
      <nav className="nav__links" role="navigation" aria-label="Story sections">
        {STATES.map((s, i) => (
          <button
            key={s}
            type="button"
            className={`nav__link ${i === active ? "is-active" : ""}`}
            onClick={() => handleJump(MARKS[i]!)}
            aria-current={i === active ? "true" : undefined}
            aria-label={`Jump to section ${i + 1}: ${s}`}
          >
            {s}
          </button>
        ))}
      </nav>
      <span className="nav__meta" aria-label={`Scroll progress ${Math.round(p * 100)} percent`}>
        {String(Math.round(p * 100)).padStart(3, "0")}%
      </span>
    </header>
  );
}
