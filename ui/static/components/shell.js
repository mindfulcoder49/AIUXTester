import { computed, useRoute } from "../lib/vue-globals.js";
import { store, logout } from "../lib/app-state.js";
import { authenticatedNavItems, go } from "../lib/navigation.js";

const shelllessPaths = new Set(["/", "/login", "/register"]);

export const AppShell = {
  setup() {
    const route = useRoute();
    const showShell = computed(() => !!store.token && !shelllessPaths.has(route.path));
    const navItems = computed(() => authenticatedNavItems(store.user?.role === "admin"));
    const activePath = computed(() => route.path);

    const navigate = (path) => go(path);
    const isActive = (path) => activePath.value === path || activePath.value.startsWith(`${path}/`);
    const handleLogout = () => {
      logout();
      go("/");
    };

    return {
      store,
      showShell,
      navItems,
      activePath,
      navigate,
      isActive,
      handleLogout,
    };
  },
  template: `
    <div class="app-frame">
      <div class="app-backdrop">
        <div class="app-glow app-glow--one"></div>
        <div class="app-glow app-glow--two"></div>
        <div class="app-grid"></div>
      </div>

      <header v-if="showShell" class="shell-bar">
        <div class="shell-bar__brand" @click="navigate('/app')">
          <span class="shell-bar__eyebrow">AIUXTester</span>
          <strong>Test Command</strong>
        </div>

        <nav class="shell-nav">
          <button
            v-for="item in navItems"
            :key="item.path"
            class="shell-nav__item"
            :class="{ 'is-active': isActive(item.path) }"
            @click="navigate(item.path)"
          >
            {{ item.label }}
          </button>
        </nav>

        <div class="shell-user">
          <div class="shell-user__meta">
            <strong>{{ store.user?.email }}</strong>
            <span>{{ store.user?.tier }} tier</span>
          </div>
          <button class="button button--ghost" @click="handleLogout">Logout</button>
        </div>
      </header>

      <main class="app-main" :class="{ 'app-main--shell': showShell }">
        <router-view />
      </main>
    </div>
  `,
};
