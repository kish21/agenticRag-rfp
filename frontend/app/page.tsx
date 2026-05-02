"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

export default function Home() {
  const router = useRouter();
  const [rfpFile, setRfpFile] = useState<File | null>(null);
  const [vendorFiles, setVendorFiles] = useState<FileList | null>(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState("");

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!rfpFile || !vendorFiles || vendorFiles.length === 0) {
      setError("Please select an RFP file and at least one vendor file.");
      return;
    }
    setUploading(true);
    setError("");
    try {
      const form = new FormData();
      form.append("rfp", rfpFile);
      for (let i = 0; i < vendorFiles.length; i++) {
        form.append("vendors", vendorFiles[i]);
      }
      const token = localStorage.getItem("access_token");
      const res = await fetch("/api/v1/evaluate/start", {
        method: "POST",
        headers: token ? { Authorization: `Bearer ${token}` } : {},
        body: form,
      });
      if (!res.ok) throw new Error(`Upload failed: ${res.status}`);
      const data = await res.json();
      router.push(`/${data.run_id}/confirm`);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setUploading(false);
    }
  }

  return (
    <main className="min-h-screen bg-slate-50 flex items-center justify-center p-8">
      <div className="bg-white rounded-xl shadow-lg p-8 w-full max-w-lg">
        <h1 className="text-2xl font-bold text-slate-800 mb-2">
          RFP Evaluation Platform
        </h1>
        <p className="text-slate-500 mb-6">
          Upload your RFP and vendor responses to begin automated evaluation.
        </p>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">
              RFP Document
            </label>
            <input
              type="file"
              accept=".pdf,.docx"
              onChange={(e) => setRfpFile(e.target.files?.[0] ?? null)}
              className="block w-full text-sm text-slate-600 file:mr-4 file:py-2 file:px-4 file:rounded file:border-0 file:bg-blue-50 file:text-blue-700 hover:file:bg-blue-100"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">
              Vendor Responses (one or more)
            </label>
            <input
              type="file"
              accept=".pdf,.docx"
              multiple
              onChange={(e) => setVendorFiles(e.target.files)}
              className="block w-full text-sm text-slate-600 file:mr-4 file:py-2 file:px-4 file:rounded file:border-0 file:bg-blue-50 file:text-blue-700 hover:file:bg-blue-100"
            />
          </div>
          {error && (
            <p className="text-sm text-red-600 bg-red-50 rounded p-2">{error}</p>
          )}
          <button
            type="submit"
            disabled={uploading}
            className="w-full py-2 px-4 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {uploading ? "Uploading..." : "Start Evaluation"}
          </button>
        </form>
      </div>
    </main>
  );
}
