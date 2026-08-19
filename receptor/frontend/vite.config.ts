import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// En desarrollo el dev server (5174) delega /api y /ws al backend Express (3000).
// En producción Express sirve directamente el contenido de dist/.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5174,
    proxy: {
      "/api": { target: "http://127.0.0.1:3000", changeOrigin: true },
      "/ws": { target: "ws://127.0.0.1:3000", ws: true },
    },
  },
  build: { outDir: "dist", emptyOutDir: true },
});
