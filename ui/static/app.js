import {
  createApp,
  createRouter,
  createWebHashHistory,
} from "./lib/vue-globals.js";
import { loadUser, store } from "./lib/app-state.js";
import { publicPaths } from "./lib/navigation.js";
import { AppShell } from "./components/shell.js";
import { Home } from "./pages/home.js";
import { Login, Register } from "./pages/auth.js";
import { Dashboard } from "./pages/dashboard.js";
import { SessionDetail } from "./pages/session-detail.js";
import { Docs, Costs, Admin } from "./pages/secondary.js";
import { CompetitionList, CompetitionDetail } from "./pages/competitions.js";

const routes = [
  { path: "/", component: Home },
  { path: "/docs", component: Docs },
  { path: "/costs", component: Costs },
  { path: "/login", component: Login },
  { path: "/register", component: Register },
  { path: "/app", component: Dashboard },
  { path: "/sessions/:id", component: SessionDetail },
  { path: "/admin", component: Admin },
  { path: "/competitions", component: CompetitionList },
  { path: "/competitions/:id", component: CompetitionDetail },
];

const router = createRouter({
  history: createWebHashHistory(),
  routes,
  scrollBehavior() {
    return { top: 0 };
  },
});

router.beforeEach(async (to) => {
  if (!store.user) await loadUser();
  if (!store.token && !publicPaths.has(to.path)) return "/login";
  if (to.path === "/admin" && store.user?.role !== "admin") return "/";
  return true;
});

createApp(AppShell).use(router).mount("#app");
