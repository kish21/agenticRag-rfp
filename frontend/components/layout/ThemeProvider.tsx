"use client";

import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { type ThemeId, DEFAULT_THEME, THEMES, applyThemeVars } from "@/lib/theme";

interface ThemeContextValue {
  themeId:  ThemeId;
  setTheme: (id: ThemeId) => void;
  isDark:   boolean;
}

const ThemeContext = createContext<ThemeContextValue>({
  themeId:  DEFAULT_THEME,
  setTheme: () => {},
  isDark:   THEMES[DEFAULT_THEME].isDark,
});

const STORAGE_KEY = "meridian-theme-v2";

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [themeId, setThemeId] = useState<ThemeId>(DEFAULT_THEME);

  useEffect(() => {
    // Mount-only read of persisted theme from localStorage. This is the
    // canonical client-only initialization pattern: external state
    // (localStorage) -> React state on first mount. useSyncExternalStore
    // would require a stable subscribe callback that localStorage does not
    // provide. Fires exactly once per mount; no cascading-render risk.
    const stored = localStorage.getItem(STORAGE_KEY) as ThemeId | null;
    const id = stored && stored in THEMES ? stored : DEFAULT_THEME;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setThemeId(id);
    applyThemeVars(id);
  }, []);

  function setTheme(id: ThemeId) {
    setThemeId(id);
    applyThemeVars(id);
    localStorage.setItem(STORAGE_KEY, id);
  }

  return (
    <ThemeContext.Provider value={{ themeId, setTheme, isDark: THEMES[themeId].isDark }}>
      {children}
    </ThemeContext.Provider>
  );
}

export function useThemeContext() {
  return useContext(ThemeContext);
}
