import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";

const api = process.env.API_PROXY ?? "http://127.0.0.1:8010";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) } },
  define: { global: "globalThis" },
  server: {
    port: 5180,
    strictPort: true,
    proxy: {
      "/api": { target: api, changeOrigin: false },
      "/v1": { target: api, changeOrigin: false },
      "/tonconnect-manifest.json": { target: api },
    },
  },
  build: {
    target: "es2022",
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes("@tonconnect") || id.includes("@ton/")) return "ton";
          if (id.includes("recharts") || id.includes("d3-")) return "charts";
          return undefined;
        },
      },
    },
  },
  test: {
    environment: "jsdom",
    include: ["src/**/*.test.{ts,tsx}"],
  },
});
