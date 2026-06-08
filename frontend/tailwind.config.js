/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#172026",
        field: "#f7f8f5",
        line: "#d9ded6",
        pine: "#2f5d50",
        coral: "#d76952",
        gold: "#b9892d"
      }
    }
  },
  plugins: []
};

