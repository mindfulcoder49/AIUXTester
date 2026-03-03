import { describe, it, expect } from "vitest";
import { allowedConfigKeysForTier, filterConfigForTier } from "./app-utils.js";


describe("config filtering", () => {
  it("returns correct keys for free", () => {
    expect(allowedConfigKeysForTier("free")).toEqual([
      "mode",
      "max_steps",
      "stop_on_first_error",
    ]);
  });

  it("filters config for basic", () => {
    const cfg = {
      mode: "desktop",
      max_steps: 100,
      stop_on_first_error: false,
      max_history_actions: 10,
      loop_detection_enabled: true,
      loop_detection_window: 12,
      postmortem_depth: "deep",
    };
    const filtered = filterConfigForTier(cfg, "basic");
    expect(filtered.postmortem_depth).toBeUndefined();
    expect(filtered.max_history_actions).toBe(10);
  });

  it("filters config for pro", () => {
    const cfg = {
      mode: "desktop",
      max_steps: 100,
      stop_on_first_error: false,
      custom_system_prompt_preamble: "x",
    };
    const filtered = filterConfigForTier(cfg, "pro");
    expect(filtered.custom_system_prompt_preamble).toBe("x");
  });

  it("returns all expected keys for basic", () => {
    expect(allowedConfigKeysForTier("basic")).toEqual([
      "mode",
      "max_steps",
      "stop_on_first_error",
      "max_history_actions",
      "loop_detection_enabled",
      "loop_detection_window",
    ]);
  });

  it("returns all expected keys for pro", () => {
    expect(allowedConfigKeysForTier("pro")).toEqual([
      "mode",
      "max_steps",
      "stop_on_first_error",
      "max_history_actions",
      "loop_detection_enabled",
      "loop_detection_window",
      "postmortem_depth",
      "custom_system_prompt_preamble",
    ]);
  });

  it("drops unknown keys from filtered output", () => {
    const cfg = {
      mode: "desktop",
      max_steps: 50,
      stop_on_first_error: false,
      unknown_key: "should-drop",
    };
    const filtered = filterConfigForTier(cfg, "free");
    expect(filtered.unknown_key).toBeUndefined();
    expect(filtered.mode).toBe("desktop");
  });

  it("treats unknown tier as pro-level filtering", () => {
    const cfg = {
      mode: "desktop",
      max_steps: 100,
      stop_on_first_error: false,
      custom_system_prompt_preamble: "custom",
    };
    const filtered = filterConfigForTier(cfg, "enterprise");
    expect(filtered.custom_system_prompt_preamble).toBe("custom");
  });
});
