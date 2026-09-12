import { createFileRoute, Outlet, redirect } from "@tanstack/react-router";
import { useEffect } from "react";
import { Sidebar } from "@/components/dashboard/Sidebar";
import { TopBar } from "@/components/dashboard/TopBar";
import { useSessionStore, ensureBackendAuth } from "@/store/session-store";
import { supabase } from "@/lib/supabase";

export const Route = createFileRoute("/dashboard")({
  ssr: false,
  // Auth guard — check Supabase session before allowing access. Also waits
  // for the backend JWT bridge here (not just in the store's init()/login()),
  // because beforeLoad is the one point the router actually awaits before
  // mounting any nested page — a page-level useEffect would run too late and
  // race real API calls against a not-yet-populated token.
  beforeLoad: async () => {
    const { data: { session } } = await supabase.auth.getSession();
    if (!session) {
      throw redirect({ to: "/" });
    }
    await ensureBackendAuth();
  },
  component: DashboardLayout,
});

function DashboardLayout() {
  const init = useSessionStore((s) => s.init);

  useEffect(() => {
    let cleanup: (() => void) | undefined;
    init().then((fn) => { cleanup = fn; });
    return () => cleanup?.();
  }, [init]);

  return (
    <div className="ug-shell">
      <Sidebar />
      <div className="ug-main">
        <TopBar />
        <main className="ug-page">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
