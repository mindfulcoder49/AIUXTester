import { createRouter, createWebHashHistory } from "vue-router";
import HomeView from "./views/HomeView.vue";
import AuthView from "./views/AuthView.vue";
import DashboardView from "./views/DashboardView.vue";
import SessionDetailView from "./views/SessionDetailView.vue";
import DocsView from "./views/DocsView.vue";
import CostsView from "./views/CostsView.vue";
import AdminView from "./views/AdminView.vue";
import CompetitionsView from "./views/CompetitionsView.vue";
import CompetitionDetailView from "./views/CompetitionDetailView.vue";
import CompetitionRecapView from "./views/CompetitionRecapView.vue";
import ResetPasswordView from "./views/ResetPasswordView.vue";
import MagicView from "./views/MagicView.vue";
import { ensureUserLoaded, state } from "./lib/store.js";

const routes = [
  { path: "/", component: HomeView },
  { path: "/login", component: AuthView, props: { mode: "login" } },
  { path: "/register", component: AuthView, props: { mode: "register" } },
  { path: "/forgot-password", component: ResetPasswordView },
  { path: "/reset-password", component: ResetPasswordView },
  { path: "/magic", component: MagicView },
  { path: "/app", component: DashboardView },
  { path: "/sessions/:id", component: SessionDetailView },
  { path: "/docs", component: DocsView },
  { path: "/costs", component: CostsView },
  { path: "/admin", component: AdminView },
  { path: "/competitions", component: CompetitionsView },
  { path: "/competitions/:id", component: CompetitionDetailView },
  { path: "/competitions/:id/recap", component: CompetitionRecapView },
];

const publicPaths = new Set(["/", "/login", "/register", "/forgot-password", "/reset-password", "/magic"]);

const router = createRouter({
  history: createWebHashHistory(),
  routes,
  scrollBehavior() {
    return { top: 0 };
  },
});

router.beforeEach(async (to) => {
  await ensureUserLoaded();
  if (!state.token && !publicPaths.has(to.path)) {
    return "/login";
  }
  if (to.path === "/admin" && state.user?.role !== "admin") {
    return "/";
  }
  return true;
});

export default router;
