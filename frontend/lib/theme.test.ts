import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// themeStore holds module-level state (theme/initialized/listeners) that only reads localStorage
// once, on first use -- clearing localStorage between tests isn't enough to isolate them, since
// the module itself stays cached and "already initialized" across test cases. vi.resetModules()
// + a fresh dynamic import per test gives each one a genuinely clean module instance instead.
async function freshThemeStore(): Promise<typeof import("./theme").themeStore> {
  vi.resetModules();
  const mod = await import("./theme");
  return mod.themeStore;
}

describe("themeStore", () => {
  beforeEach(() => {
    window.localStorage.clear();
    document.documentElement.classList.remove("dark");
  });

  afterEach(() => {
    window.localStorage.clear();
    document.documentElement.classList.remove("dark");
  });

  it("defaults to light when nothing is stored and the system doesn't prefer dark", async () => {
    const themeStore = await freshThemeStore();
    expect(themeStore.getSnapshot()).toBe("light");
    expect(document.documentElement.classList.contains("dark")).toBe(false);
  });

  it("toggling applies the dark class and persists the choice", async () => {
    const themeStore = await freshThemeStore();
    themeStore.toggle();
    expect(themeStore.getSnapshot()).toBe("dark");
    expect(document.documentElement.classList.contains("dark")).toBe(true);
    expect(window.localStorage.getItem("agent_ops_theme")).toBe("dark");
  });

  it("toggling twice returns to light and removes the dark class", async () => {
    const themeStore = await freshThemeStore();
    themeStore.toggle();
    themeStore.toggle();
    expect(themeStore.getSnapshot()).toBe("light");
    expect(document.documentElement.classList.contains("dark")).toBe(false);
  });

  it("notifies subscribers on toggle", async () => {
    const themeStore = await freshThemeStore();
    let calls = 0;
    const unsubscribe = themeStore.subscribe(() => {
      calls += 1;
    });

    themeStore.toggle();

    expect(calls).toBe(1);
    unsubscribe();
  });

  it("picks up an already-stored preference on first read", async () => {
    window.localStorage.setItem("agent_ops_theme", "dark");
    const themeStore = await freshThemeStore();
    expect(themeStore.getSnapshot()).toBe("dark");
  });

  it("getServerSnapshot is always light, for SSR consistency", async () => {
    const themeStore = await freshThemeStore();
    expect(themeStore.getServerSnapshot()).toBe("light");
  });
});
