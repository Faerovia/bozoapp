import { redirect } from "next/navigation";

// Root → dashboard (middleware ochraňuje /dashboard, redirect na /login pokud není token)
export default function Home() {
  redirect("/dashboard");
}
