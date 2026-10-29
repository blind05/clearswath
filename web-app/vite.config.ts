import path from "node:path";
import stylex from "@stylexjs/unplugin";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The build lands in web/dist, which the FastAPI app serves at /. In development, /api goes to `uvicorn app.api:app`.
const src = path.resolve(import.meta.dirname, "src");

// StyleX compiles our styles and Astryx's into one stylesheet at build time.
export default defineConfig({
  plugins: [stylex.vite({ aliases: { "@/*": [path.join(src, "*")] } }), react()],
  resolve: { alias: { "@": src } },
  build: { outDir: "../web/dist", emptyOutDir: true },
  server: { proxy: { "/api": "http://127.0.0.1:8000" } },
});
