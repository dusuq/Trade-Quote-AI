import { redirect } from "next/navigation";

export default function Home() {
  // The shell lives under /dashboard; unauthenticated users are sent to /login
  // by the app-group layout once auth wiring lands. For now, land on the dashboard.
  redirect("/dashboard");
}
