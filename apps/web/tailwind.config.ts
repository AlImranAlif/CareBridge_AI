import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#18343b",
        teal: { 50: "#eff9f7", 100: "#d8f0eb", 500: "#258b7c", 600: "#1e7469", 700: "#195e57" },
        canvas: "#f5f8f7",
      },
      boxShadow: { soft: "0 10px 35px rgba(24, 52, 59, 0.06)" },
    },
  },
  plugins: [],
};

export default config;
