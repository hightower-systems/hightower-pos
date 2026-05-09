import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev proxy targets:
//   /api/*          -> POS Service on :8081 (the user's local Sentry takes :8080).
//   /print-agent/*  -> Print Agent on 127.0.0.1:9100. Origin is forged to the
//                       production POS web URL so the agent's Origin gate
//                       doesn't 403 the Vite dev server.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://localhost:8081",
        changeOrigin: false,
      },
      "/print-agent": {
        target: "http://127.0.0.1:9100",
        rewrite: (path) => path.replace(/^\/print-agent/, ""),
        configure: (proxy) => {
          proxy.on("proxyReq", (proxyReq) => {
            proxyReq.setHeader("Origin", "http://pos-vm.local:8080");
          });
        },
      },
    },
  },
  build: {
    outDir: "dist",
    sourcemap: true,
  },
});
