<script setup>
import { computed, ref } from "vue";
import { useRouter } from "vue-router";
import PageHero from "../components/PageHero.vue";
import { apiRequest, loadUser, setToken } from "../lib/store.js";

const props = defineProps({
  mode: {
    type: String,
    required: true,
  },
});

const router     = useRouter();
const email      = ref("");
const password   = ref("");
const error      = ref("");
const loginTab   = ref("password"); // "password" | "magic"
const magicSent  = ref(false);
const magicLoading = ref(false);

const isRegister = computed(() => props.mode === "register");

async function submit() {
  error.value = "";
  try {
    const response = await apiRequest(`/auth/${isRegister.value ? "register" : "login"}`, {
      method: "POST",
      body: JSON.stringify({ email: email.value, password: password.value }),
    });
    setToken(response.access_token);
    await loadUser();
    router.push("/app");
  } catch (err) {
    error.value = err.message || "Unable to authenticate";
  }
}

async function sendMagicLink() {
  error.value    = "";
  magicLoading.value = true;
  try {
    await apiRequest("/auth/magic-link", {
      method: "POST",
      body: JSON.stringify({ email: email.value }),
    });
    magicSent.value = true;
  } catch (err) {
    error.value = err.message || "Unable to send link.";
  } finally {
    magicLoading.value = false;
  }
}
</script>

<template>
  <div class="page-shell space-y-6">
    <PageHero
      kicker="Account access"
      :title="isRegister ? 'Create a workspace for saved runs and competitions.' : 'Sign in to continue testing and reviewing evidence.'"
      :body="isRegister
        ? 'The Vue frontend uses the same auth and API surface as the current app, so your data and permissions carry over.'
        : 'Once authenticated, you can launch sessions, review past evidence, and manage competitions from the same account.'"
    />

    <section class="mx-auto w-full max-w-xl surface-card p-6 sm:p-8">
      <h2 class="font-display text-3xl font-bold text-slate-900">
        {{ isRegister ? "Create account" : "Login" }}
      </h2>

      <!-- Login tabs (only shown on login page) -->
      <div v-if="!isRegister" class="mt-4 flex gap-1 rounded-xl bg-slate-100 p-1">
        <button
          class="flex-1 rounded-lg py-1.5 text-sm font-medium transition"
          :class="loginTab === 'password' ? 'bg-white shadow text-slate-900' : 'text-slate-500 hover:text-slate-700'"
          @click="loginTab = 'password'; error = ''; magicSent = false"
        >
          Password
        </button>
        <button
          class="flex-1 rounded-lg py-1.5 text-sm font-medium transition"
          :class="loginTab === 'magic' ? 'bg-white shadow text-slate-900' : 'text-slate-500 hover:text-slate-700'"
          @click="loginTab = 'magic'; error = ''; magicSent = false"
        >
          Magic link
        </button>
      </div>

      <!-- Password login / register form -->
      <form v-if="isRegister || loginTab === 'password'" class="mt-5 space-y-5" @submit.prevent="submit">
        <div>
          <label class="field-label">Email</label>
          <input v-model="email" type="email" class="field-input" placeholder="you@example.com" required />
        </div>
        <div>
          <label class="field-label">Password</label>
          <input v-model="password" type="password" class="field-input" placeholder="Password" required />
        </div>
        <button class="primary-button w-full">
          {{ isRegister ? "Create account" : "Login" }}
        </button>
        <p v-if="error" class="text-sm font-medium text-rose-600">{{ error }}</p>
        <div v-if="!isRegister" class="text-center">
          <button type="button" class="text-sm text-slate-500 hover:text-slate-700 underline"
            @click="router.push('/forgot-password')">
            Forgot password?
          </button>
        </div>
      </form>

      <!-- Magic link form -->
      <div v-else-if="loginTab === 'magic'" class="mt-5">
        <template v-if="magicSent">
          <p class="text-sm font-medium text-emerald-600">Check your email — a login link is on its way. It expires in 15 minutes.</p>
          <button class="ghost-button mt-4 w-full" @click="magicSent = false; email = ''">Send another</button>
        </template>
        <form v-else class="space-y-4" @submit.prevent="sendMagicLink">
          <div>
            <label class="field-label">Email</label>
            <input v-model="email" type="email" class="field-input" placeholder="you@example.com" required />
          </div>
          <button class="primary-button w-full" :disabled="magicLoading">
            {{ magicLoading ? "Sending…" : "Send me a magic link" }}
          </button>
          <p v-if="error" class="text-sm font-medium text-rose-600">{{ error }}</p>
        </form>
      </div>

      <div class="mt-6 flex flex-wrap items-center justify-between gap-3 text-sm text-slate-500">
        <span>{{ isRegister ? "Already have an account?" : "Need an account?" }}</span>
        <button class="ghost-button" @click="router.push(isRegister ? '/login' : '/register')">
          {{ isRegister ? "Back to login" : "Create account" }}
        </button>
      </div>
    </section>
  </div>
</template>
