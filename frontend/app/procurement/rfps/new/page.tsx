"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { isLoggedIn } from "@/lib/api";
import { useBreakpoint } from "@/lib/hooks";
import { CreateRFPForm } from "@/components/features/rfp/CreateRFPForm";

export default function NewRFPPage() {
  const router = useRouter();
  const bp = useBreakpoint();
  const [authChecked, setAuthChecked] = useState(false);

  useEffect(() => {
    // Mount-only auth guard. The setState flips authChecked from false to
    // true ONCE per mount, after we confirm the cookie session exists.
    // The intermediate blank-render is intentional (prevents flicker of
    // protected content before redirect).
    if (!isLoggedIn()) {
      router.replace("/login");
      return;
    }
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setAuthChecked(true);
  }, [router]);

  if (!authChecked) {
    return (
      <div
        className="min-h-screen flex items-center justify-center"
        style={{ background: "var(--bg-gradient)" }}
      />
    );
  }

  const padY = bp === "mobile" ? 24 : bp === "tablet" ? 32 : 48;
  const padX = bp === "mobile" ? 20 : bp === "tablet" ? 24 : 32;

  return (
    <main
      className="min-h-screen"
      style={{
        background: "var(--bg-gradient)",
        padding: `${padY}px ${padX}px`,
      }}
    >
      <div className="mx-auto" style={{ maxWidth: 720 }}>
        <CreateRFPForm />
      </div>
    </main>
  );
}
