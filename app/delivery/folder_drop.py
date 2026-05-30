"""
Folder-drop delivery channel.

Writes the report PDF (or HTML when no PDF is available) to a target directory —
a local path today, the seam for S3 / Azure Blob later. Useful for customers who
collect reports in a shared drive instead of email.

    target = {"path": "/srv/reports/acme"}
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from app.delivery.base import DeliveryChannel, DeliveryPayload, DeliveryResult


class FolderDropChannel(DeliveryChannel):
    name = "folder"

    def dispatch(self, payload: DeliveryPayload, target: dict[str, Any]) -> DeliveryResult:
        dest_dir = (target or {}).get("path", "").strip()
        if not dest_dir:
            return DeliveryResult.failure(self.name, "", "no destination path in target")

        try:
            base = Path(dest_dir)
            base.mkdir(parents=True, exist_ok=True)
            if payload.pdf_bytes:
                out = base / payload.filename
                out.write_bytes(payload.pdf_bytes)
            else:
                # No PDF (e.g. weasyprint unavailable) — drop the HTML instead.
                out = base / (Path(payload.filename).stem + ".html")
                out.write_text(payload.html_body or payload.summary, encoding="utf-8")
        except Exception as exc:  # noqa: BLE001 — never raise; the dispatcher retries
            return DeliveryResult.failure(self.name, dest_dir, f"{type(exc).__name__}: {exc}")

        return DeliveryResult.success(self.name, str(out))
