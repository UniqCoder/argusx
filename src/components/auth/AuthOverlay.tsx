import { useEffect } from "react";
import { useAuthStore } from "@/store/auth-store";
import { AuthPanel } from "./AuthPanel";
import { AuthScene } from "./AuthScene";

export function AuthOverlay() {
  const { isOpen, close } = useAuthStore();

  /* ESC to close */
  useEffect(() => {
    if (!isOpen) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") close();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [isOpen, close]);

  /* prevent body scroll while open */
  useEffect(() => {
    document.body.style.overflow = isOpen ? "hidden" : "";
    return () => {
      document.body.style.overflow = "";
    };
  }, [isOpen]);

  if (!isOpen) return null;

  return (
    /* backdrop */
    <div
      className="auth-overlay"
      role="dialog"
      aria-modal="true"
      aria-label="Sign up or sign in"
      onClick={(e) => {
        if (e.target === e.currentTarget) close();
      }}
    >
      <div className="auth-overlay__panel">
        {/* close button */}
        <button
          className="auth-overlay__close"
          onClick={close}
          aria-label="Close"
          type="button"
        >
          <svg
            width="18"
            height="18"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
          >
            <line x1="18" y1="6" x2="6" y2="18" />
            <line x1="6" y1="6" x2="18" y2="18" />
          </svg>
        </button>

        {/* left — auth form */}
        <div className="auth-overlay__left">
          <AuthPanel />
        </div>

        {/* right — 3-D scene */}
        <div className="auth-overlay__right">
          <AuthScene />
        </div>
      </div>
    </div>
  );
}
