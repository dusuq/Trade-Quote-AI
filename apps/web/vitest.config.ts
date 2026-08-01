import { defineConfig } from "vitest/config";
import path from "node:path";

export default defineConfig({
  test: {
    // Stays "node" so the existing lib tests are untouched. Component tests
    // opt into jsdom per-file with a `@vitest-environment jsdom` docblock,
    // which keeps a DOM out of tests that don't need one.
    environment: "node",
    include: ["src/**/*.test.ts", "src/**/*.test.tsx"],
  },
  // Next.js compiles JSX itself (tsconfig sets jsx: "preserve"), so vitest's
  // esbuild needs to be told which runtime to use for .tsx test files.
  esbuild: { jsx: "automatic" },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
});
