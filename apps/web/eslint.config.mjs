import config from "@tradequote/config/eslint";
import tseslint from "typescript-eslint";

export default tseslint.config(
  { ignores: ["next-env.d.ts", ".next/**", "dist/**", "coverage/**"] },
  ...config
);
