"use client";

import { useTranslations } from "next-intl";
import ChangeFeed from "@/features/catalogue/components/ChangeFeed";
import { Panel } from "@/features/catalogue/components/ui";

export default function RecentChangesPage() {
    const t = useTranslations();
    return (
        <div className="space-y-4">
            <div>
                <h1 className="font-semibold text-[24px] text-black">{t("recent_changes")}</h1>
                <p className="text-[14px] text-gray-600">{t("cat_feed_hint")}</p>
            </div>
            <Panel>
                <ChangeFeed showSubjectFilter />
            </Panel>
        </div>
    );
}
