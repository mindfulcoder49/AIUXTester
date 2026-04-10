export const publicPaths = new Set(["/", "/docs", "/costs", "/login", "/register"]);

export function go(path) {
  window.location.hash = `#${path}`;
}

export function back(defaultPath = "/app") {
  if (window.history.length > 1) {
    window.history.back();
    return;
  }
  go(defaultPath);
}

export function authenticatedNavItems(isAdmin) {
  const items = [
    { path: "/app", label: "Dashboard" },
    { path: "/competitions", label: "Competitions" },
    { path: "/docs", label: "Docs" },
    { path: "/costs", label: "Cost" },
  ];
  if (isAdmin) {
    items.push({ path: "/admin", label: "Admin" });
  }
  return items;
}
