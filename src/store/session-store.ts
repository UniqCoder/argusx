// ============================================================
// ARGUS — Session Store
// Auth via Supabase for the dashboard gate. The backend has its own,
// separate JWT (see ensureBackendAuth below) that real API calls need.
// ============================================================
import { create } from "zustand";
import { supabase } from "@/lib/supabase";
import { login as backendLogin, tokenStore } from "@/lib/api";

// ── Backend JWT bridge ──────────────────────────────────────────────────────
// The backend (sih-backend) has no real multi-user auth yet — Phase 0/1 only
// accepts a single hardcoded dev credential (see auth.py / config.py:
// DEV_USER_EMAIL/DEV_USER_PASSWORD, default investigator@i4c.gov.in/devpass).
// Every Supabase account a person signs up with therefore maps to the SAME
// backend identity — fields like `assigned_investigator` on the backend won't
// reflect which real person acted. That's a real, pre-existing backend
// limitation this bridge cannot fix, only work around so real API calls carry
// a valid token instead of failing with 401s.
// Swap the two VITE_BACKEND_DEV_* vars when the backend gets real users.
export async function ensureBackendAuth(): Promise<void> {
  if (tokenStore.getAccess()) return; // already have a token — idempotent
  const email =
    (import.meta.env["VITE_BACKEND_DEV_EMAIL"] as string | undefined) ??
    "investigator@i4c.gov.in";
  const password =
    (import.meta.env["VITE_BACKEND_DEV_PASSWORD"] as string | undefined) ??
    "devpass";
  try {
    await backendLogin({ email, password });
  } catch {
    // Backend down/unreachable — Supabase auth must still succeed. Pages
    // surface this via their own offline-banner/error state on the failed
    // API calls that follow, not here.
  }
}

interface SessionState {
  isAuthenticated: boolean;
  isLoading: boolean;
  email: string | null;
  user: { email: string } | null;
  session: { access_token: string } | null;
  // Actions
  login:  (creds: { email: string; password: string }) => Promise<void>;
  signup: (creds: { email: string; password: string }) => Promise<void>;
  logout: () => Promise<void>;
  init:   () => Promise<() => void>;
}

export const useSessionStore = create<SessionState>((set) => ({
  isAuthenticated: false,
  isLoading: true,
  email: null,
  user: null,
  session: null,

  // Called once on DashboardLayout mount — restores session from Supabase
  init: async () => {
    const { data: { session } } = await supabase.auth.getSession();
    if (session) await ensureBackendAuth();
    set({
      isAuthenticated: !!session,
      isLoading: false,
      email:   session?.user?.email ?? null,
      user:    session ? { email: session.user.email ?? "" } : null,
      session: session ? { access_token: session.access_token } : null,
    });

    // Listen for Supabase auth state changes (token refresh, sign-out etc.)
    const { data: { subscription } } = supabase.auth.onAuthStateChange((_event, session) => {
      set({
        isAuthenticated: !!session,
        email:   session?.user?.email ?? null,
        user:    session ? { email: session.user.email ?? "" } : null,
        session: session ? { access_token: session.access_token } : null,
      });
    });

    return () => subscription.unsubscribe();
  },

  login: async ({ email, password }) => {
    set({ isLoading: true });
    const { data, error } = await supabase.auth.signInWithPassword({ email, password });
    if (error) {
      set({ isLoading: false });
      throw new Error(error.message);
    }
    await ensureBackendAuth();
    set({ isLoading: false });
    set({
      isAuthenticated: true,
      email:   data.user?.email ?? email,
      user:    { email: data.user?.email ?? email },
      session: { access_token: data.session.access_token },
    });
  },

  signup: async ({ email, password }) => {
    set({ isLoading: true });
    const { error } = await supabase.auth.signUp({
      email,
      password,
      options: {
        // Return the user to wherever they signed up from (prod URL on Vercel,
        // localhost in dev) instead of the Supabase dashboard's Site URL.
        emailRedirectTo: window.location.origin,
      },
    });
    set({ isLoading: false });
    if (error) throw new Error(error.message);
    // Supabase sends a confirmation email — user must verify before signing in
  },

  logout: async () => {
    await supabase.auth.signOut();
    tokenStore.clear();
    set({
      isAuthenticated: false,
      email: null,
      user: null,
      session: null,
    });
  },
}));
