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
    const stored = localStorage.getItem(STORAGE_KEY) as ThemeId | null;
    const id = stored && stored in THEMES ? stored : DEFAULT_THEME;
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
