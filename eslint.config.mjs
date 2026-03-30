import nextVitals from "eslint-config-next/core-web-vitals";

const eslintConfig = [
  {
    ignores: [".next/**", ".venv/**", "node_modules/**", "__pycache__/**"]
  },
  ...nextVitals
];

export default eslintConfig;
