import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Painel React do Analytical-Force.
// "base: './'" gera caminhos relativos no build — importante porque o
// backend (FastAPI) serve o dist/ como arquivos estáticos a partir da
// raiz do container no Hugging Face Spaces (ver src/delivery/static_app.py).
export default defineConfig({
  plugins: [react()],
  base: "./",
  build: {
    outDir: "dist",
    emptyOutDir: true,
  },
});
