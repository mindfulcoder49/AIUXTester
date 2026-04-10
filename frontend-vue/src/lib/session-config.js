export function allowedConfigKeysForTier(tier) {
  if (tier === "free") {
    return ["mode", "max_steps", "stop_on_first_error"];
  }
  if (tier === "basic") {
    return [
      "mode",
      "max_steps",
      "stop_on_first_error",
      "max_history_actions",
      "loop_detection_enabled",
      "loop_detection_window",
    ];
  }
  return [
    "mode",
    "max_steps",
    "stop_on_first_error",
    "max_history_actions",
    "loop_detection_enabled",
    "loop_detection_window",
    "postmortem_depth",
    "custom_system_prompt_preamble",
  ];
}

export function filterConfigForTier(config, tier) {
  const allowed = allowedConfigKeysForTier(tier);
  const output = {};
  allowed.forEach((key) => {
    if (key in config) output[key] = config[key];
  });
  return output;
}
