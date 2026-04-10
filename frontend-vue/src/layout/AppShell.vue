<script setup>
import { computed } from "vue";
import { RouterLink, RouterView, useRoute, useRouter } from "vue-router";
import { clearAuth, isAdmin, state } from "../lib/store.js";

const route = useRoute();
const router = useRouter();

const navItems = computed(() => {
  const items = [
    { path: "/app", label: "Dashboard" },
    { path: "/competitions", label: "Competitions" },
    { path: "/docs", label: "Docs" },
    { path: "/costs", label: "Cost" },
  ];
  if (isAdmin.value) items.push({ path: "/admin", label: "Admin" });
  return items;
});

const hideShellOn = new Set(["/", "/login", "/register"]);
const showShell = computed(() => state.token && !hideShellOn.has(route.path));

function logout() {
  clearAuth();
  router.push("/");
}

function isRouteActive(path) {
  return route.path === path || route.path.startsWith(`${path}/`);
}
</script>

<template>
  <div class="min-h-screen">
    <header v-if="showShell" class="page-shell pb-0">
      <div class="surface-card bg-slate-900/90 px-4 py-4 text-white sm:px-6">
        <div class="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <p class="section-kicker text-slate-300">AIUXTester</p>
            <p class="font-display text-2xl font-bold">Flow Stack</p>
          </div>

          <nav class="flex flex-wrap items-center gap-2">
            <RouterLink
              v-for="item in navItems"
              :key="item.path"
              :to="item.path"
              class="rounded-full px-4 py-2 text-sm font-medium transition"
              :class="isRouteActive(item.path)
                ? 'bg-white/12 text-white'
                : 'text-slate-300 hover:bg-white/8 hover:text-white'"
            >
              {{ item.label }}
            </RouterLink>
          </nav>

          <div class="flex flex-wrap items-center gap-3">
            <div class="min-w-0">
              <p class="truncate text-sm font-semibold">{{ state.user?.email }}</p>
              <p class="text-xs text-slate-300">{{ state.user?.tier }} tier</p>
            </div>
            <button class="ghost-button border-white/20 bg-white/10 text-white hover:bg-white/15" @click="logout">
              Logout
            </button>
          </div>
        </div>
      </div>
    </header>

    <main>
      <RouterView />
    </main>
  </div>
</template>
