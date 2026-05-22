/**
 * Next.js API route — SSE proxy for dev/agent log stream.
 *
 * Same buffering fix as the evaluate/[runId]/status route.
 */
import { NextRequest, NextResponse } from "next/server";

const BACKEND = process.env.BACKEND_URL ?? "http://localhost:8000";

export async function GET(request: NextRequest) {
  const cookie   = request.headers.get("cookie") ?? "";
  const runId    = request.nextUrl.searchParams.get("run_id");
  const qs       = runId ? `?run_id=${encodeURIComponent(runId)}` : "";

  let upstream: Response;
  try {
    upstream = await fetch(`${BACKEND}/api/v1/logs/stream${qs}`, {
      headers: { cookie },
    });
  } catch {
    return NextResponse.json({ detail: "Backend unreachable" }, { status: 502 });
  }

  if (!upstream.ok) {
    const text = await upstream.text();
    return new NextResponse(text, { status: upstream.status });
  }

  return new NextResponse(upstream.body, {
    status: 200,
    headers: {
      "Content-Type":      "text/event-stream",
      "Cache-Control":     "no-cache, no-transform",
      "X-Accel-Buffering": "no",
      Connection:          "keep-alive",
    },
  });
}
