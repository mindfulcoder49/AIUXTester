import { ref } from "../lib/vue-globals.js";
import { apiRequest, loadUser, setToken } from "../lib/app-state.js";
import { go } from "../lib/navigation.js";

function buildAuthPage(mode) {
  const isRegister = mode === "register";
  return {
    template: `
      <div class="page page--auth">
        <section class="auth-card">
          <div class="auth-card__intro">
            <p class="section-kicker">Account Access</p>
            <h1>${isRegister ? "Create your workspace" : "Welcome back"}</h1>
            <p>${isRegister
              ? "Create an account to store runs, compare sessions, and submit finished tests into competitions."
              : "Sign in to launch new runs, review evidence, and manage competitions from the command surface."}</p>
          </div>

          <form class="auth-form" @submit.prevent="submit">
            <div class="field-stack">
              <label class="field-label">Email</label>
              <input v-model="email" type="email" placeholder="you@example.com" required />
            </div>
            <div class="field-stack">
              <label class="field-label">Password</label>
              <input v-model="password" type="password" placeholder="Password" required />
            </div>
            <button class="button button--primary auth-form__submit">${isRegister ? "Create account" : "Login"}</button>
            <p class="form-feedback form-feedback--error" v-if="error">{{ error }}</p>
          </form>

          <div class="auth-card__footer">
            <span>${isRegister ? "Already have an account?" : "Need an account?"}</span>
            <button class="button button--ghost" @click="swap">${isRegister ? "Back to login" : "Create account"}</button>
          </div>
        </section>
      </div>
    `,
    setup() {
      const email = ref("");
      const password = ref("");
      const error = ref("");

      const submit = async () => {
        error.value = "";
        try {
          const data = await apiRequest(`/auth/${isRegister ? "register" : "login"}`, {
            method: "POST",
            body: JSON.stringify({ email: email.value, password: password.value }),
          });
          setToken(data.access_token);
          await loadUser();
          go("/app");
        } catch (err) {
          error.value = err.message || "Unable to authenticate";
        }
      };

      return {
        email,
        password,
        error,
        submit,
        swap: () => go(isRegister ? "/login" : "/register"),
      };
    },
  };
}

export const Login = buildAuthPage("login");
export const Register = buildAuthPage("register");
