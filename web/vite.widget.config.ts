import { defineConfig } from "vite";

// One-file embed script: <script src="https://host/checkout.js"></script>
export default defineConfig({
  build: {
    emptyOutDir: false,
    lib: {
      entry: "src/widget/embed.ts",
      name: "TonCheckout",
      formats: ["iife"],
      fileName: () => "checkout.js",
    },
  },
});
