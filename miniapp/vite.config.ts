import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// В разработке запросы /api/* уходят на локальный сервер платформы (порт 8000)
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": { target: "http://localhost:8000", rewrite: (p) => p.replace(/^\/api/, "") },
    },
  },
});
