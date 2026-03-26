import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react-swc";
import path from "path";

export default defineConfig(({ command, mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const backendTarget = env.VITE_DEV_BACKEND_URL || env.VITE_API_BASE_URL || env.VITE_BACKEND_URL || "";
  const devPort = Number(env.VITE_DEV_PORT) || 5173;

  if (command === "serve" && !backendTarget) {
    throw new Error("VITE_DEV_BACKEND_URL is required to proxy /api requests in dev.");
  }

  return {
    server: command === "serve"
      ? {
        host: "::",
        port: devPort,
        proxy: {
          "/api": {
            target: backendTarget,
            changeOrigin: true,
          },
          "/health": {
            target: backendTarget,
            changeOrigin: true,
          },
        },
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
