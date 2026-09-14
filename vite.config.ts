// @lovable.dev/vite-tanstack-config already includes the following — do NOT add them manually
// or the app will break with duplicate plugins:
//   - TanStack devtools (dev-only, first), tanstackStart, viteReact, tailwindcss, tsConfigPaths,
//     nitro (build-only using cloudflare as a default target), VITE_* env injection, @ path alias,
//     React/TanStack dedupe, error logger plugins, and sandbox detection (port/host/strictPort).
// You can pass additional config via defineConfig({ vite: { ... }, etc... }) if needed.
import type { ConfigEnv } from "vite";
import { defineConfig } from "@lovable.dev/vite-tanstack-config";

const baseConfig = defineConfig({
  tanstackStart: {
    // Redirect TanStack Start's bundled server entry to src/server.ts (our SSR error wrapper).
    // nitro/vite builds from this
    server: { entry: "server" },
  },
});

// @lovable.dev/vite-tanstack-config hardcodes server.port to 8080 for the
// Lovable sandbox and never reads process.env.PORT, so a local dev harness
// that assigns a different port (because 8080 is already taken by another
// server) has no way to tell Vite to use it — Vite just falls back to its
// own "next free port" increment (8081, 8082, ...), which the harness never
// finds. Only override when PORT is actually set by such a harness; the
// real Lovable sandbox build/dev path is untouched.
export default async (env: ConfigEnv) => {
  const config = await baseConfig(env);
  const portOverride = process.env["PORT"];
  if (portOverride) {
    config.server = {
      ...config.server,
      port: Number(portOverride),
      strictPort: false,
    };
  }
  return config;
};
