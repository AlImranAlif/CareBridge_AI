import Link from "next/link";
import { Icon } from "@/components/icon";
import type { ApiStatus } from "@/lib/api";

const records = [
  { type: "Laboratory report", name: "Annual wellness panel", date: "May 18, 2025", tag: "Reviewed", tone: "green", icon: "✳" },
  { type: "Prescription", name: "Medication overview", date: "May 06, 2025", tag: "Processing", tone: "blue", icon: "＋" },
  { type: "Visit summary", name: "Primary care visit", date: "Apr 22, 2025", tag: "Reviewed", tone: "green", icon: "⌂" },
];

export function Dashboard({ apiStatus }: { apiStatus: ApiStatus }) {
  return <main className="min-w-0 flex-1 px-5 py-6 sm:px-8 lg:px-10 lg:py-9">
    <header className="flex items-center justify-between gap-4">
      <div className="relative hidden w-full max-w-[330px] sm:block"><Icon name="search" className="absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400"/><input aria-label="Search your records" placeholder="Search your health records" className="h-10 w-full rounded-xl border border-slate-200 bg-white pl-10 pr-3 text-xs outline-none placeholder:text-slate-400 focus:border-teal-500 focus:ring-2 focus:ring-teal-100"/></div>
      <div className="ml-auto flex items-center gap-3"><div className="flex items-center gap-2 rounded-full border border-slate-200 bg-white px-3 py-2 text-[11px] text-slate-500 lg:hidden"><span className={`h-1.5 w-1.5 rounded-full ${apiStatus === "online" ? "bg-emerald-500" : "bg-amber-400"}`}/>API {apiStatus}</div><button aria-label="Notifications" className="rounded-xl border border-slate-200 bg-white p-2.5 text-slate-500"><Icon name="bell" className="h-[17px] w-[17px]"/></button><div className="flex h-9 w-9 items-center justify-center rounded-full bg-[#dceee9] text-xs font-semibold text-teal-700" aria-label="Demo profile">CB</div></div>
    </header>

    <section className="mt-9 flex flex-col justify-between gap-5 sm:flex-row sm:items-end">
      <div><p className="text-xs font-medium text-slate-400">Thursday, November 20, 2026</p><h1 className="mt-2 text-[27px] font-semibold tracking-tight text-ink sm:text-[32px]">Good morning<span className="text-teal-600">.</span></h1><p className="mt-1.5 text-sm text-slate-500">Your health, organized in one place.</p></div>
      <button className="inline-flex h-11 items-center justify-center gap-2 rounded-xl bg-teal-600 px-4 text-[13px] font-semibold text-white shadow-sm transition hover:bg-teal-700"><Icon name="plus" className="h-4 w-4"/>Add a document</button>
    </section>

    <section aria-label="Health record summary" className="mt-7 grid gap-4 sm:grid-cols-3">
      <article className="rounded-2xl border border-slate-100 bg-white p-5 shadow-soft"><div className="flex items-center justify-between"><span className="text-[12px] font-medium text-slate-500">Total documents</span><span className="rounded-lg bg-teal-50 p-2 text-teal-700"><Icon name="file" className="h-4 w-4"/></span></div><div className="mt-4 text-[27px] font-semibold tracking-tight text-ink">12</div><p className="mt-1 text-[11px] text-slate-400">Across 4 categories</p></article>
      <article className="rounded-2xl border border-slate-100 bg-white p-5 shadow-soft"><div className="flex items-center justify-between"><span className="text-[12px] font-medium text-slate-500">Timeline entries</span><span className="rounded-lg bg-[#f1f2fc] p-2 text-indigo-600"><Icon name="clock" className="h-4 w-4"/></span></div><div className="mt-4 text-[27px] font-semibold tracking-tight text-ink">8</div><p className="mt-1 text-[11px] text-slate-400">Your health history at a glance</p></article>
      <article className="rounded-2xl border border-slate-100 bg-white p-5 shadow-soft"><div className="flex items-center justify-between"><span className="text-[12px] font-medium text-slate-500">To review</span><span className="rounded-lg bg-amber-50 p-2 text-amber-600"><Icon name="check" className="h-4 w-4"/></span></div><div className="mt-4 text-[27px] font-semibold tracking-tight text-ink">2</div><p className="mt-1 text-[11px] text-slate-400">A quick check keeps things accurate</p></article>
    </section>

    <section className="mt-6 overflow-hidden rounded-2xl bg-[#eaf5f2] p-5 sm:p-6"><div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-center"><div className="flex gap-4"><div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-[14px] bg-white/80 text-teal-700"><Icon name="spark" className="h-5 w-5"/></div><div><p className="text-sm font-semibold text-ink">A clearer picture starts here</p><p className="mt-1 max-w-lg text-xs leading-5 text-slate-600">Bring your health documents together and make it easier to find what matters, when you need it.</p></div></div><Link href="/documents" className="inline-flex items-center gap-2 self-start whitespace-nowrap text-xs font-semibold text-teal-700 hover:text-teal-900 sm:self-center">Explore your records <Icon name="arrow" className="h-4 w-4"/></Link></div></section>

    <section className="mt-8"><div className="flex items-end justify-between"><div><h2 className="text-[16px] font-semibold tracking-tight text-ink">Recent documents</h2><p className="mt-1 text-xs text-slate-400">Your latest additions and updates</p></div><Link href="/documents" className="text-xs font-semibold text-teal-700 hover:text-teal-900">View all</Link></div>
      <div className="mt-4 overflow-hidden rounded-2xl border border-slate-100 bg-white shadow-soft"><div className="hidden grid-cols-[1fr_150px_110px_32px] gap-4 border-b border-slate-100 px-5 py-3 text-[10px] font-semibold uppercase tracking-[0.13em] text-slate-400 sm:grid"><span>Document</span><span>Added</span><span>Status</span><span/></div>
        {records.map((record) => <article key={record.name} className="grid grid-cols-[1fr_32px] items-center gap-3 border-b border-slate-50 px-4 py-4 last:border-0 sm:grid-cols-[1fr_150px_110px_32px] sm:px-5"><div className="flex min-w-0 items-center gap-3"><span className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl text-lg ${record.tone === "green" ? "bg-teal-50 text-teal-700" : "bg-blue-50 text-blue-600"}`}>{record.icon}</span><div className="min-w-0"><p className="truncate text-[13px] font-semibold text-ink">{record.name}</p><p className="mt-1 text-[11px] text-slate-400">{record.type}</p></div></div><span className="hidden text-[11px] text-slate-500 sm:block">{record.date}</span><span className={`hidden w-fit rounded-full px-2.5 py-1 text-[10px] font-semibold sm:block ${record.tag === "Reviewed" ? "bg-emerald-50 text-emerald-700" : "bg-blue-50 text-blue-700"}`}>{record.tag}</span><button aria-label={`More options for ${record.name}`} className="rounded-lg p-2 text-slate-400 hover:bg-slate-50"><Icon name="dots" className="h-4 w-4"/></button></article>)}
      </div>
    </section>
    <footer className="mt-8 flex flex-col gap-1 border-t border-slate-100 py-4 text-[10px] text-slate-400 sm:flex-row sm:justify-between"><span>CareBridge AI · A personal health record workspace</span><span>Demo dashboard · Sample content only</span></footer>
  </main>;
}
