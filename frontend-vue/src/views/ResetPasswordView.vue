<script setup>
import { computed, onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import PageHero from "../components/PageHero.vue";
import { apiRequest } from "../lib/store.js";

const route  = useRoute();
const router = useRouter();

// If ?token= is in the URL we're in "set new password" mode,
// otherwise we're in "request reset" mode.
const token       = computed(() => route.query.token || "");
const mode        = computed(() => token.value ? "reset" : "request");

const email       = ref("");
const password    = ref("");
const password2   = ref("");
const loading     = ref(false);
const error       = ref("");
const success     = ref(false);

async function submitRequest() {
  error.value   = "";
  loading.value = true;
  try {
    await apiRequest("/auth/request-password-reset", {
      method: "POST",
      body: JSON.stringify({ email: email.value }),
    });
    success.value = true;
  } catch (err) {
    error.value = err.message || "Something went wrong.";
  } finally {
    loading.value = false;
  }
}

async function submitReset() {
  error.value = "";
  if (password.value !== password2.value) {
    error.value = "Passwords don't match.";
    return;
  }
  loading.value = true;
  try {
    await apiRequest("/auth/reset-password", {
      method: "POST",
      body: JSON.stringify({ token: token.value, password: password.value }),
    });
    success.value = true;
  } catch (err) {
    error.value = err.message || "Reset failed. The link may have expired.";
  } finally {
    loading.value = false;
  }
}
</script>

<template>
  <div class="page-shell space-y-6">
    <PageHero
      kicker="Account"
      :title="mode === 'reset' ? 'Set a new password' : 'Forgot your password?'"
      body="Enter your email and we'll send you a reset link."
    />

    <section class="mx-auto w-full max-w-xl surface-card p-6 sm:p-8">

      <!-- Request sent -->
      <template v-if="success && mode === 'request'">
        <h2 class="font-display text-2xl font-bold text-slate-900">Check your email</h2>
        <p class="mt-3 text-sm text-slate-600">
          If an account exists for <strong>{{ email }}</strong>, a reset link is on its way. It expires in 15 minutes.
        </p>
        <button class="ghost-button mt-5" @click="router.push('/login')">Back to login</button>
      </template>

      <!-- Reset done -->
      <template v-else-if="success && mode === 'reset'">
        <h2 class="font-display text-2xl font-bold text-slate-900">Password updated</h2>
        <p class="mt-3 text-sm text-slate-600">Your password has been changed. You can now sign in.</p>
        <button class="primary-button mt-5" @click="router.push('/login')">Go to login</button>
      </template>

      <!-- Request form -->
      <template v-else-if="mode === 'request'">
        <h2 class="font-display text-2xl font-bold text-slate-900">Reset password</h2>
        <form class="mt-5 space-y-4" @submit.prevent="submitRequest">
          <div>
            <label class="field-label">Email</label>
            <input v-model="email" type="email" class="field-input" placeholder="you@example.com" required />
          </div>
          <button class="primary-button w-full" :disabled="loading">
            {{ loading ? "Sending…" : "Send reset link" }}
          </button>
          <p v-if="error" class="text-sm font-medium text-rose-600">{{ error }}</p>
        </form>
        <button class="ghost-button mt-4 w-full" @click="router.push('/login')">Back to login</button>
      </template>

      <!-- Set new password form -->
      <template v-else>
        <h2 class="font-display text-2xl font-bold text-slate-900">Choose a new password</h2>
        <form class="mt-5 space-y-4" @submit.prevent="submitReset">
          <div>
            <label class="field-label">New password</label>
            <input v-model="password" type="password" class="field-input" placeholder="At least 8 characters" required minlength="8" />
          </div>
          <div>
            <label class="field-label">Confirm password</label>
            <input v-model="password2" type="password" class="field-input" placeholder="Repeat password" required />
          </div>
          <button class="primary-button w-full" :disabled="loading">
            {{ loading ? "Saving…" : "Set new password" }}
          </button>
          <p v-if="error" class="text-sm font-medium text-rose-600">{{ error }}</p>
        </form>
      </template>

    </section>
  </div>
</template>
