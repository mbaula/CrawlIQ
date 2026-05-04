"use client";

import { useTheme } from "next-themes";
import { useEffect, useState } from "react";

export function ThemeToggle() {
  const { resolvedTheme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);

  useEffect(() => setMounted(true), []);

  if (!mounted) {
    return (
      <span
        className="inline-flex h-8 w-14 items-center justify-center rounded border border-rule bg-paper font-mono text-xs text-muted"
        aria-hidden
      >
        …
      </span>
    );
  }

  const isDark = resolvedTheme === "dark";

  return (
    <button
      type="button"
      onClick={() => setTheme(isDark ? "light" : "dark")}
      className="inline-flex h-8 items-center gap-2 rounded border border-rule bg-paper px-2.5 font-mono text-xs text-ink transition-colors duration-150 hover:border-accent hover:text-accent focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
      aria-label={isDark ? "Switch to light theme" : "Switch to dark theme"}
    >
      <span className="select-none">{isDark ? "Light" : "Dark"}</span>
    </button>
  );
}
