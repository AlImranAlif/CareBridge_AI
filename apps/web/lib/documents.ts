import { apiUrl } from "@/lib/api";

export type ExtractedFact = { id: string; field: string; value: string; unit: string; page: number; excerpt: string; review_status: "needs_review" | "confirmed" | "rejected" };
export type DocumentRecord = { id: string; filename: string; media_type: string; size_bytes: number; sha256: string; doc_type: string; doc_date: string | null; extraction_method: string; status: string; uploaded_at: string; facts: ExtractedFact[]; source_text: string };

async function checked<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let message = "অনুরোধ সম্পন্ন করা যায়নি।";
    try { message = (await response.json()).message ?? message; } catch { /* use safe fallback */ }
    throw new Error(message);
  }
  return response.json() as Promise<T>;
}

export async function listDocuments(): Promise<DocumentRecord[]> {
  return checked(await fetch(apiUrl("/documents"), { cache: "no-store" }));
}

export async function uploadDocument(file: File): Promise<DocumentRecord> {
  const body = new FormData(); body.append("file", file);
  return checked(await fetch(apiUrl("/documents/upload"), { method: "POST", body, cache: "no-store" }));
}

export async function reviewFact(documentId: string, factId: string, status: "confirmed" | "rejected"): Promise<ExtractedFact> {
  return checked(await fetch(apiUrl(`/documents/${encodeURIComponent(documentId)}/facts/${encodeURIComponent(factId)}`), { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ status }), cache: "no-store" }));
}
