export default defineNuxtConfig({
  compatibilityDate: "2026-11-10",
  css: ["~/assets/css/tokens.css", "~/assets/css/main.css"],
  app: {
    head: { htmlAttrs: { lang: "fr" }, title: "antaudiro — Prévision d’affluence — Isère" },
  },
  devtools: { enabled: false },
  runtimeConfig: {
    public: {
      apiBase: "http://localhost:8000",
    },
  },
});
