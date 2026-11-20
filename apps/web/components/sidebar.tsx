import Link from "next/link";
import { Icon } from "@/components/icon";
import type { ApiStatus } from "@/lib/api";

const navigation = [
  { label: "সংক্ষিপ্ত বিবরণ", href: "/", icon: "grid" as const, active: true },
  { label: "নথি ও ইতিহাস", href: "/documents", icon: "file" as const },
  { label: "স্বাস্থ্য টাইমলাইন", href: "/timeline", icon: "clock" as const },
  { label: "রিপোর্ট", href: "/reports", icon: "chart" as const },
  { label: "সেটিংস", href: "/settings", icon: "settings" as const },
];

export function Sidebar({ apiStatus }: { apiStatus: ApiStatus }) {
  return (
    <aside className="flex w-full shrink-0 flex-col border-b border-slate-100 bg-white px-5 py-5 lg:min-h-screen lg:w-[248px] lg:border-b-0 lg:border-r lg:px-5 lg:py-7">
      <Link href="/" className="flex items-center gap-3 px-1">
        <span className="flex h-10 w-10 items-center justify-center rounded-[14px] bg-teal-600 text-white"><span className="text-xl font-semibold">+</span></span>
        <span><span className="block text-[17px] font-semibold tracking-tight text-ink">CareBridge</span><span className="block text-[10px] font-semibold text-slate-400">ব্যক্তিগত স্বাস্থ্য</span></span>
      </Link>
      <div className="mt-9 hidden text-[10px] font-semibold text-slate-400 lg:block">আপনার সংগ্রহ</div>
      <nav aria-label="Main navigation" className="mt-4 flex gap-1 overflow-x-auto lg:flex-col">
        {navigation.map((item) => <Link key={item.label} href={item.href} aria-current={item.active ? "page" : undefined} className={`flex shrink-0 items-center gap-3 rounded-xl px-3 py-2.5 text-[13px] font-medium transition ${item.active ? "bg-teal-50 text-teal-700" : "text-slate-500 hover:bg-slate-50 hover:text-ink"}`}><Icon name={item.icon} className="h-[18px] w-[18px]" />{item.label}</Link>)}
      </nav>
      <div className="mt-auto hidden rounded-2xl border border-slate-100 bg-slate-50/80 p-4 lg:block">
        <div className="flex items-center justify-between"><span className="text-xs font-semibold text-ink">সিস্টেমের অবস্থা</span><span className={`h-2 w-2 rounded-full ${apiStatus === "online" ? "bg-emerald-500" : "bg-amber-400"}`} /></div>
        <p className="mt-2 text-[11px] leading-5 text-slate-500">API {apiStatus === "online" ? "সংযুক্ত" : "বন্ধ"}</p>
        <p className="text-[10px] text-slate-400">ডেভেলপমেন্ট প্রদর্শনী</p>
      </div>
    </aside>
  );
}
