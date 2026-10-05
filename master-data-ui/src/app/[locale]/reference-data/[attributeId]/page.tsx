import { getLocale } from "next-intl/server";
import { redirect } from "@/i18n/navigation";

/** Old route of a dataset's page. */
export default async function ReferenceDataItemRedirect({ params }: { params: Promise<{ attributeId: string }> }) {
    const { attributeId } = await params;
    const locale = await getLocale();
    redirect({ href: `/datasets/${attributeId}`, locale });
}
