import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// In development the API runs on :8000 (uvicorn); in production VITE_API_URL points at it.
export default defineConfig({
  plugins: [react()],
  // MapLibre alone is ~800 kB minified; one bundle is fine for a single-page dashboard.
  build: { chunkSizeWarningLimit: 2000 },
  server: {
    proxy: { "/api": "http://localhost:8000" },
  },
});
