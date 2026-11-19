import Link from "next/link";

const sections: Record<string, { title: string; description: string }> = {
  documents: { title: "Your documents", description: "A home for the records you choose to organize." },
  timeline: { title: "Health timeline", description: "A chronological view of your health history will live here." },
  reports: { title: "Reports", description: "Helpful overviews of your records will appear here." },
  settings: { title: "Profile & settings", description: "Manage your preferences and account details here." },
};

export default async function PlaceholderPage({ params }: { params: Promise<{ section: string }> }) {
  const { section } = await params;
  const content = sections[section] ?? { title: "Coming soon", description: "This area is part of the CareBridge workspace." };
  return <main className="flex-1 px-5 py-10 sm:px-8 lg:px-10"><div className="mx-auto mt-12 max-w-xl rounded-3xl border border-slate-100 bg-white p-8 text-center shadow-soft sm:p-12"><div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-teal-50 text-teal-700"><span className="text-xl">✳</span></div><h1 className="mt-6 text-2xl font-semibold tracking-tight text-ink">{content.title}</h1><p className="mx-auto mt-2 max-w-sm text-sm leading-6 text-slate-500">{content.description}</p><p className="mt-5 text-xs text-slate-400">This section is a placeholder in the Phase 1 foundation.</p><Link href="/" className="mt-7 inline-flex items-center rounded-xl bg-teal-600 px-4 py-2.5 text-xs font-semibold text-white hover:bg-teal-700">Back to overview</Link></div></main>;
}
