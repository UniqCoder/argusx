import { createFileRoute, Outlet, redirect } from "@tanstack/react-router";
import { useEffect } from "react";
import { Sidebar } from "@/components/dashboard/Sidebar";
import { TopBar } from "@/components/dashboard/TopBar";
import { useSessionStore } from "@/store/session-store";
import { supabase } from "@/lib/supabase";

export const Route = createFileRoute("/dashboard")({
  ssr: false,
  // Auth guard — check Supabase session before allowing access
  beforeLoad: async () => {
    const { data: { session } } = await supabase.auth.getSession();
    if (!session) {
      throw redirect({ to: "/" });
    }
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
