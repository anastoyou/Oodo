/** @type {import('tailwindcss').Config} */
export default {
  important: "#custom-react-pdp-root",
  corePlugins: {
    preflight: false,
  },
  content: [
    "./src/**/*.{ts,tsx,js,jsx}",
    "../addons/custom_store*/custom_pdp/*/react/**/*.{ts,tsx,js,jsx}",
  ],
  theme: {
    extend: {},
  },
  plugins: [],
};
