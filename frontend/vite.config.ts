import { defineConfig, loadEnv, type Plugin } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

declare const process: { env: Record<string, string | undefined> }; // no @types/node

/** CSP meta tag for production builds (dev needs inline scripts for HMR). frame-ancestors must be a header. */
function csp(apiBase: string): Plugin {
  const api = apiBase.match(/^https?:\/\/[^/]+/)?.[0] ?? "";
  const policy = [
    "default-src 'self'",
    "script-src 'self'",
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
    "font-src 'self' https://fonts.gstatic.com",
    "img-src 'self' data: blob: https:",
    `connect-src 'self' ${api} https://fullnode.mainnet.sui.io https://api.slush.app https://api.enoki.mystenlabs.com`,
    "frame-src 'none'",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
  ].join("; ").replace(/\s+;/g, ";");
  return {
    name: "marketrecall-csp",
    apply: "build",
    transformIndexHtml: (html) =>
      html.replace('<meta charset="UTF-8" />', `<meta charset="UTF-8" />\n    <meta http-equiv="Content-Security-Policy" content="${policy}" />`),
  };
}

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, ".", "VITE_");
  return {
    plugins: [react(), tailwindcss(), csp(env.VITE_API_BASE ?? "")],
    server: {
      proxy: {
        "/api": {
          target: process.env.API_PROXY ?? "http://127.0.0.1:8000",
          changeOrigin: true,
        },
      },
    },
    preview: {
      proxy: {
        "/api": { target: process.env.API_PROXY ?? "http://127.0.0.1:8000", changeOrigin: true },
      },
    },
  };
});
