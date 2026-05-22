/**
 * Next.js API route — SSE proxy for agent status stream.
 *
 * Next.js Turbopack dev-proxy buffers streaming responses (rewrites wait
 * for the connection to close before forwarding). This route bypasses that
 * by piping the FastAPI SSE stream directly as a ReadableStream response.
 */
import { NextRequest, NextResponse } from "next/server";

const BACKEND = process.env.BACKEND_URL ?? "http://localhost:8000";

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ runId: string }> }
) {
  const { runId } = await params;
  const cookie = request.headers.get("cookie") ?? "";

  let upstream: Response;
  try {
    upstream = await fetch(`${BACKEND}/api/v1/evaluate/${runId}/status`, {
      headers: { cookie },
      // Node fetch keeps the connection open for streaming
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
