import { getLocale } from "next-intl/server";
import { redirect } from "@/i18n/navigation";

export default async function Home() {
  const locale = await getLocale();
  redirect({ href: "/geo-locations", locale });
}
