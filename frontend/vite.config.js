import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Builds React "islands" into a single file Django serves as a static asset.
export default defineConfig({
  plugins: [react()],
  define: { "process.env.NODE_ENV": '"production"' },
  build: {
    outDir: "../static/js",
    emptyOutDir: false,
    lib: {
      entry: "src/main.jsx",
      name: "IadebayoIslands",
      formats: ["iife"],
      fileName: () => "islands.js",
    },
  },
});
