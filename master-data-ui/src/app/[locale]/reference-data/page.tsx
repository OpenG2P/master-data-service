import { getLocale } from "next-intl/server";
import { redirect } from "@/i18n/navigation";

/** Old route of the Datasets page. */
export default async function ReferenceDataRedirect() {
    const locale = await getLocale();
    redirect({ href: "/datasets", locale });
}
