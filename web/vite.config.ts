/// <reference types="vitest/config" />
import react from "@vitejs/plugin-react";
import { defineConfig, searchForWorkspaceRoot } from "vite";

const apiTarget = process.env.COMMANDER_API ?? "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // The arm twin imports the URDF's STL meshes straight from ../digital_twin.
    fs: { allow: [searchForWorkspaceRoot(process.cwd()), "../digital_twin/sboter4u_model/meshes"] },
    proxy: {
      "/api": { target: apiTarget, changeOrigin: true },
    },
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
    // three.js is a lazily loaded chunk used only by the arm twin.
    chunkSizeWarningLimit: 650,
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    css: false,
    coverage: {
      provider: "v8",
      include: ["src/**/*.{ts,tsx}"],
      exclude: ["src/test/**", "src/main.tsx", "src/**/*.test.{ts,tsx}"],
      reporter: ["text", "lcov"],
    },
  },
});
