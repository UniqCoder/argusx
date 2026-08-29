// ============================================================
// ARGUS — Session Store
// Auth via Supabase. Dashboard backend needs no token.
// ============================================================
import { create } from "zustand";
import { supabase } from "@/lib/supabase";

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
    set({ isLoading: false });
    if (error) throw new Error(error.message);
    set({
      isAuthenticated: true,
      email:   data.user?.email ?? email,
      user:    { email: data.user?.email ?? email },
      session: { access_token: data.session.access_token },
    });
  },

  signup: async ({ email, password }) => {
    set({ isLoading: true });
    const { error } = await supabase.auth.signUp({ email, password });
    set({ isLoading: false });
    if (error) throw new Error(error.message);
    // Supabase sends a confirmation email — user must verify before signing in
  },

  logout: async () => {
    await supabase.auth.signOut();
    set({
      isAuthenticated: false,
      email: null,
      user: null,
      session: null,
    });
  },
}));
