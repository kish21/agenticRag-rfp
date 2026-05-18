// ── Breakpoint hook — SSR-safe, resize-aware ─────────────────────────────────
// mobile  : < 640px
// tablet  : 640px – 1023px
// desktop : ≥ 1024px

"use client";

import { useState, useEffect } from "react";

export type Breakpoint = "mobile" | "tablet" | "desktop";

function getBreakpoint(width: number): Breakpoint {
  if (width < 640) return "mobile";
  if (width < 1024) return "tablet";
  return "desktop";
}

export function useBreakpoint(): Breakpoint {
  const [bp, setBp] = useState<Breakpoint>("desktop"); // SSR-safe default

  useEffect(() => {
    function update() {
      setBp(getBreakpoint(window.innerWidth));
    }
    update();
    window.addEventListener("resize", update);
    return () => window.removeEventListener("resize", update);
  }, []);

  return bp;
}

export function useIsMobile(): boolean {
  return useBreakpoint() === "mobile";
}

export function useIsDesktop(): boolean {
  return useBreakpoint() === "desktop";
}
