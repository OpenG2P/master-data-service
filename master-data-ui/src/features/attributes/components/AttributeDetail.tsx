"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { useRouter } from "@/i18n/navigation";
import { ArrowLeft, Pencil } from "lucide-react";
import Can from "@/components/Can";
import LoadingState from "@/components/LoadingState";
import { useAllAttributes } from "../hooks";
import AttributeDialog from "./AttributeDialog";
import AttributeValuesView from "./AttributeValuesView";
import type { Attribute } from "../types";

const REFERENCE_DATA_ACTIONS = {
    edit: "referenceData:edit",
};

interface AttributeDetailProps {
    attributeId: string;
}

export default function AttributeDetail({ attributeId }: AttributeDetailProps) {
    const t = useTranslations();
    const router = useRouter();
    const [showEdit, setShowEdit] = useState(false);

    const { attributes, loading, refresh } = useAllAttributes();

    const attribute: Attribute | undefined = attributes.find(
        (a) => a.attribute_id === attributeId,
    );

    if (loading && !attribute) {
        return <LoadingState loaderOnly />;
    }

    if (!attribute) {
        return (
            <div className="flex h-full items-center justify-center bg-black text-white/40 text-[16px]">
                {t("no_attributes")}
            </div>
        );
    }

    return (
        <div className="flex h-full min-h-0 flex-col">
            {/* Top strip */}
            <div className="shrink-0 bg-black border-[#5A5A5A] px-5 py-0 pt-4 flex items-center gap-4">
                <button
                    type="button"
                    onClick={() => router.push("/reference-data")}
                    className="flex items-center gap-2 text-[16px] font-medium text-white/60 hover:text-white transition-colors"
                >
                    <ArrowLeft size={18} />
                    {t("reference_data")}
                </button>
                <span className="text-[#5A5A5A]">/</span>
                <span className="text-[16px] font-semibold text-white">
                    {attribute.attribute_display || attribute.attribute_code}
                </span>

                <div className="ml-auto flex items-center gap-3">
                    <span className="text-[14px] rounded-full border border-[#5A5A5A] px-3 py-1 text-white/50">
                        {attribute.is_hierarchical ? t("hierarchical") : t("flat")}
                    </span>
                    <Can action={REFERENCE_DATA_ACTIONS.edit}>
                        <button
                            type="button"
                            onClick={() => setShowEdit(true)}
                            className="flex items-center gap-2 h-9 rounded-[8px] border border-[#5A5A5A] px-4 text-[16px] font-medium text-white/70 hover:bg-white/10"
                        >
                            <Pencil size={15} />
                            {t("edit")}
                        </button>
                    </Can>
                </div>
            </div>

            {/* Values */}
            <div className="flex min-h-0 flex-1 flex-col bg-black p-5">
                <AttributeValuesView
                    key={`${attribute.attribute_id}-${attribute.is_hierarchical}`}
                    attribute={attribute}
                />
            </div>

            {/* Edit dialog */}
            <AttributeDialog
                open={showEdit}
                mode="edit"
                attribute={attribute}
                onClose={() => setShowEdit(false)}
                onSuccess={() => {
                    refresh();
                    setShowEdit(false);
                }}
            />
        </div>
    );
}
