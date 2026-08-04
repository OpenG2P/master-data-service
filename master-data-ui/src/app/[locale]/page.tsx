"use client";

import { useAuth } from "@/context/Authcontext";
import { useTranslations } from "next-intl";

export default function Home() {
  const { user, logout } = useAuth();
  const t = useTranslations();

  return (
    <main style={{ padding: "2rem", fontFamily: "sans-serif" }}>
      <h1>Master Data UI</h1>
      <p>
        Signed in as:{" "}
        {user?.name || user?.preferred_username || user?.email || "user"}
      </p>
      <button type="button" onClick={logout}>
        {t("logout")}
      </button>
    </main>
  );
}
