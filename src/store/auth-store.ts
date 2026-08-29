import { create } from "zustand";

type AuthTab = "signup" | "signin";

interface AuthState {
  isOpen: boolean;
  tab: AuthTab;
  open: (tab?: AuthTab) => void;
  close: () => void;
  setTab: (tab: AuthTab) => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  isOpen: false,
  tab: "signup",
  open: (tab = "signup") => set({ isOpen: true, tab }),
  close: () => set({ isOpen: false }),
  setTab: (tab) => set({ tab }),
}));
