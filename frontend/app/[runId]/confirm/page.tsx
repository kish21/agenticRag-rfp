"use client";

import { useRouter, useParams } from "next/navigation";
import { ConfirmSetupPage } from "@/components/features/ConfirmSetupPage";

export default function Page() {
  const router = useRouter();
  const { runId } = useParams<{ runId: string }>();

  if (!runId) return null;

  return (
    <div style={{ minHeight: "100vh", padding: "48px 32px", background: "var(--bg-gradient)" }}>
      <ConfirmSetupPage
        runId={runId}
        onConfirmed={() => router.push(`/${runId}/progress`)}
        onBack={() => router.back()}
        onAuth401={() => router.push("/login")}
      />
    </div>
  );
}
