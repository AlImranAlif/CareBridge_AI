import { Dashboard } from "@/components/dashboard";
import { getApiStatus } from "@/lib/api";
export default async function WorkspacePage(){ return <Dashboard apiStatus={await getApiStatus()}/>; }
