<script setup>
import { onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { apiRequest, loadUser, setToken } from "../lib/store.js";

const route  = useRoute();
const router = useRouter();
const error  = ref("");

onMounted(async () => {
  const token = route.query.token || "";
  if (!token) {
    error.value = "No login token found in this link.";
    return;
  }
  try {
    const response = await apiRequest(`/auth/magic-link/verify?token=${encodeURIComponent(token)}`);
    setToken(response.access_token);
    await loadUser();
    router.replace("/app");
  } catch (err) {
    error.value = err.message || "This link is invalid or has expired. Please request a new one.";
  }
});
</script>

<template>
  <div class="page-shell flex items-center justify-center min-h-[60vh]">
    <div class="text-center space-y-4">
      <template v-if="!error">
        <p class="text-lg font-medium text-slate-700">Signing you in…</p>
        <p class="text-sm text-slate-500">Just a moment.</p>
      </template>
      <template v-else>
        <p class="text-lg font-semibold text-rose-600">Link expired or invalid</p>
        <p class="text-sm text-slate-600">{{ error }}</p>
        <div class="flex gap-3 justify-center pt-2">
          <a href="#/login" class="ghost-button">Back to login</a>
          <a href="#/login" class="primary-button">Request a new link</a>
        </div>
      </template>
    </div>
  </div>
</template>
