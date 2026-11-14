import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev server proxies the API and WebSocket to the ASTRA backend (python run.py).
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": "http://127.0.0.1:8000",
      "/ws": { target: "ws://127.0.0.1:8000", ws: true },
    },
  },
  build: { outDir: "dist", assetsDir: "assets", sourcemap: false },
});
