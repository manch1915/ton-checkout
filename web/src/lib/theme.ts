import { useCallback, useEffect, useState } from "react";

export type Theme = "light" | "dark";
const KEY = "tc-theme";

function initial(): Theme {
  try {
    const saved = localStorage.getItem(KEY);
    if (saved === "light" || saved === "dark") return saved;
  } catch {
    // Storage can be blocked, fall back to the system preference.
  }
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export function applyTheme(theme: Theme): void {
  document.documentElement.dataset.theme = theme;
}

export function useTheme(): [Theme, () => void] {
  const [theme, setTheme] = useState<Theme>(initial);
  useEffect(() => applyTheme(theme), [theme]);
  const toggle = useCallback(() => {
    setTheme((current) => {
      const next = current === "dark" ? "light" : "dark";
      try {
        localStorage.setItem(KEY, next);
      } catch {
        // Not critical.
      }
      return next;
    });
  }, []);
  return [theme, toggle];
}
