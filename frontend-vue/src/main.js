import { createApp } from "vue";
import App from "./App.vue";
import router from "./router.js";
import "./style.css";
import { bootstrapAuth } from "./lib/store.js";

async function init() {
  await bootstrapAuth();
  createApp(App).use(router).mount("#app");
}

init();
