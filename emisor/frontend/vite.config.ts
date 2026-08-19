import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// En desarrollo el dev server (5173) delega /api y /ws al backend FastAPI (8000).
// En producción FastAPI sirve directamente el contenido de dist/.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": { target: "http://127.0.0.1:8000", changeOrigin: true },
      "/ws": { target: "ws://127.0.0.1:8000", ws: true },
    },
  },
  build: { outDir: "dist", emptyOutDir: true },
});
