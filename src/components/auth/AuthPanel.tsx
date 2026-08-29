import { useState, type FormEvent } from "react";
import { useNavigate } from "@tanstack/react-router";
import { useAuthStore } from "@/store/auth-store";
import { useSessionStore } from "@/store/session-store";

/* ─── tiny inline SVG icons ─── */
const EyeIcon = ({ open }: { open: boolean }) =>
  open ? (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
      <circle cx="12" cy="12" r="3" />
    </svg>
  ) : (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19" />
      <line x1="1" y1="1" x2="23" y2="23" />
    </svg>
  );

/* ─── reusable field ─── */
function Field({
  label, id, type = "text", placeholder, value, onChange, required = true,
}: {
  label: string; id: string; type?: string; placeholder: string;
  value: string; onChange: (v: string) => void; required?: boolean;
}) {
  const [showPw, setShowPw] = useState(false);
  const isPassword = type === "password";
  const actualType = isPassword ? (showPw ? "text" : "password") : type;

  return (
    <div className="auth-field">
      <label className="auth-field__label" htmlFor={id}>{label}</label>
      <div className="auth-field__wrap">
        <input
          id={id}
          type={actualType}
          placeholder={placeholder}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          required={required}
          autoComplete={isPassword ? "current-password" : id.includes("email") ? "email" : undefined}
          className="auth-field__input"
        />
        {isPassword && (
          <button type="button" className="auth-field__eye"
            onClick={() => setShowPw((v) => !v)}
            aria-label={showPw ? "Hide password" : "Show password"}>
            <EyeIcon open={showPw} />
          </button>
        )}
      </div>
    </div>
  );
}

/* ─── Sign Up form ─── */
function SignUpForm({ onSuccess }: { onSuccess: () => void }) {
  const [email,    setEmail]    = useState("");
  const [password, setPassword] = useState("");
  const [confirm,  setConfirm]  = useState("");
  const [loading,  setLoading]  = useState(false);
  const [error,    setError]    = useState("");
  const [done,     setDone]     = useState(false);

  const { signup } = useSessionStore();

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError("");
    if (password.length < 8) { setError("Password must be at least 8 characters."); return; }
    if (password !== confirm)  { setError("Passwords do not match."); return; }
    setLoading(true);
    try {
      await signup({ email, password });
      setDone(true);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Sign up failed.");
    } finally {
      setLoading(false);
    }
  };

  if (done) {
    return (
      <div className="auth-form">
        <p className="auth-form__info" role="status" style={{ color: "var(--color-accent)" }}>
          Check your email — a confirmation link has been sent to <strong>{email}</strong>.
          Once confirmed, sign in with your credentials.
        </p>
        <button type="button" className="auth-submit" onClick={onSuccess}>
          Go to Sign In →
        </button>
      </div>
    );
  }

  return (
    <form className="auth-form" onSubmit={handleSubmit} noValidate>
      <Field label="Work email"      id="su-email"   type="email"    placeholder="officer@police.gov.in" value={email}    onChange={setEmail}    />
      <Field label="Password"        id="su-pw"      type="password" placeholder="Min 8 characters"      value={password} onChange={setPassword} />
      <Field label="Confirm password"id="su-pw2"     type="password" placeholder="Repeat password"       value={confirm}  onChange={setConfirm}  />

      {error && <p className="auth-form__error" role="alert">{error}</p>}

      <button type="submit" className="auth-submit" disabled={loading}>
        {loading && <span className="auth-submit__spinner" />}
        {loading ? "Creating account…" : "Create account →"}
      </button>

      <p className="auth-form__legal">
        By signing up you agree to Argus's terms of service and data-sovereignty policy.
      </p>
    </form>
  );
}

/* ─── Sign In form ─── */
function SignInForm({ onSuccess }: { onSuccess: () => void }) {
  const [email,    setEmail]    = useState("");
  const [password, setPassword] = useState("");
  const [loading,  setLoading]  = useState(false);
  const [error,    setError]    = useState("");

  const { login } = useSessionStore();

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await login({ email, password });
      onSuccess();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Login failed. Check your credentials.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <form className="auth-form" onSubmit={handleSubmit} noValidate>
      <Field label="Work email" id="si-email" type="email"    placeholder="officer@police.gov.in" value={email}    onChange={setEmail}    />
      <Field label="Password"   id="si-pw"    type="password" placeholder="Your password"         value={password} onChange={setPassword} />

      {error && <p className="auth-form__error" role="alert">{error}</p>}

      <button type="submit" className="auth-submit" disabled={loading}>
        {loading && <span className="auth-submit__spinner" />}
        {loading ? "Signing in…" : "Sign in →"}
      </button>
    </form>
  );
}

/* ─── AuthPanel ─── */
export function AuthPanel() {
  const { tab, setTab, close } = useAuthStore();
  const navigate = useNavigate();

  const handleSignInSuccess = () => {
    close();
    navigate({ to: "/dashboard" });
  };

  const handleSignUpSuccess = () => setTab("signin");

  return (
    <div className="auth-panel">
      {/* Brand */}
      <div className="auth-panel__brand">
        <div style={{ width: 6, height: 6, background: "var(--color-primary)", boxShadow: "var(--glow-amber)", flexShrink: 0 }} />
        <span style={{ fontSize: "0.7rem", letterSpacing: "0.32em", textTransform: "uppercase", fontWeight: 700, color: "var(--color-foreground)" }}>
          Argus
        </span>
      </div>

      {/* Heading */}
      <div className="auth-panel__heading">
        <h2 className="auth-panel__title">
          {tab === "signin" ? "Sign in" : "Create account"}
        </h2>
        <p className="auth-panel__sub">
          {tab === "signin"
            ? "Blockchain forensics for Indian law enforcement."
            : "Register your investigator account."}
        </p>
      </div>

      {/* Tab switcher */}
      <div className="auth-tabs">
        <button type="button" className={`auth-tab${tab === "signup" ? " auth-tab--active" : ""}`} onClick={() => setTab("signup")}>
          Sign up
        </button>
        <button type="button" className={`auth-tab${tab === "signin" ? " auth-tab--active" : ""}`} onClick={() => setTab("signin")}>
          Sign in
        </button>
      </div>

      {tab === "signup"
        ? <SignUpForm onSuccess={handleSignUpSuccess} />
        : <SignInForm onSuccess={handleSignInSuccess} />}
    </div>
  );
}
