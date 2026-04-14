import type { Config } from "tailwindcss";
import tailwindcssAnimate from "tailwindcss-animate";

const config: Config = {
  darkMode: ["class"],
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}", "./hooks/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#17211d",
        mint: "#1fbf9b",
        coral: "#ff6f61",
        gold: "#f5c542",
        cloud: "#f6fbf8",
      },
      boxShadow: {
        soft: "0 20px 70px rgba(23, 33, 29, 0.14)",
      },
    },
  },
  plugins: [tailwindcssAnimate],
};

export default config;
