import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#1f2933",
        moss: "#2f5d50",
        saffron: "#d99a2b",
        fog: "#f6f7f9",
        line: "#d9dee5"
      },
      boxShadow: {
        panel: "0 16px 45px rgba(31, 41, 51, 0.10)"
      }
    }
  },
  plugins: []
};

export default config;
