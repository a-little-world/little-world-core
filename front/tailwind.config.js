/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: "selector",
  content: ["./apps/admin_panel_frontend/src/**/*.{ts,tsx}"],
  prefix: "",
  daisyUI: {
    darkMode: "selector",
  },
  theme: {
    screens: {
      mid: "800px",
      "3xl": "1920px",
    },
    container: {
      center: true,
      padding: "2rem",
      screens: {
        "2xl": "1400px",
      },
    },
    extend: {
      width: {
        120: "30rem",
        140: "35rem",
        160: "40rem",
        180: "45rem",
        200: "50rem",
        240: "60rem",
        280: "70rem",
        320: "80rem",
        360: "90rem",
        400: "100rem",
      },
      zIndex: {
        60: "60",
        70: "70",
        80: "80",
        90: "90",
        100: "100",
        110: "110",
        120: "120",
        130: "130",
        140: "140",
        150: "150",
        160: "160",
        170: "170",
        180: "180",
        1000: "1000",
      },
      keyframes: {
        "accordion-down": {
          from: { height: "0" },
          to: { height: "var(--radix-accordion-content-height)" },
        },
        "accordion-up": {
          from: { height: "var(--radix-accordion-content-height)" },
          to: { height: "0" },
        },
      },
      animation: {
        "accordion-down": "accordion-down 0.2s ease-out",
        "accordion-up": "accordion-up 0.2s ease-out",
      },
    },
  },
  plugins: [
    require("tailwindcss-animate"),
    require("daisyui"),
    require("@tailwindcss/typography"),
  ],
};
