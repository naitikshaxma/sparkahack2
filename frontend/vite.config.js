import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react-swc";
import path from "path";

export default defineConfig(({ command, mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const backendTarget = env.VITE_DEV_BACKEND_URL || env.VITE_API_BASE_URL || env.VITE_BACKEND_URL || "http://127.0.0.1:8000";
  const devPort = Number(env.VITE_DEV_PORT) || 5173;
  const proxyConfig = backendTarget
    ? {
      "/api": {
        target: backendTarget,
        changeOrigin: true,
      },
      "/health": {
        target: backendTarget,
        changeOrigin: true,
      },
    }
    : undefined;

  return {
    server: command === "serve"
      ? {
        host: "::",
        port: devPort,
        proxy: proxyConfig,
        hmr: {
          overlay: false,
        },
      }
      : undefined,
    plugins: [react()],
    resolve: {
      alias: {
        "@": path.resolve(__dirname, "./src"),
      },
    },
    test: {
      environment: "jsdom",
      setupFiles: "./src/test/setup.ts",
      globals: true,
    },
  };
});
