"use client";

import { useTranslations } from "next-intl";
import { useRouter } from "@/i18n/navigation";
import { ArrowLeft } from "lucide-react";
import TableSkeleton from "@/components/TableSkeleton";
import { useAllAttributes } from "../hooks";
import AttributeValuesView from "./AttributeValuesView";
import type { Attribute } from "../types";

interface AttributeDetailProps {
    attributeId: string;
}

export default function AttributeDetail({ attributeId }: AttributeDetailProps) {
    const t = useTranslations();
    const router = useRouter();

    const { attributes, loading } = useAllAttributes();

    const attribute: Attribute | undefined = attributes.find(
        (a) => a.attribute_id === attributeId,
    );

    if (loading && !attribute) {
        return (
            <div>
                <div className="flex items-center gap-2 mb-6">
                    <button
                        type="button"
                        onClick={() => router.push("/reference-data")}
                        className="flex items-center gap-2 text-[18px] font-semibold text-black/80 hover:text-black transition-colors"
                    >
                        <ArrowLeft size={18} />
                        {t("reference_data")}
                    </button>
                    <span className="text-[22px] text-black">&gt;</span>
                    <div className="h-6 bg-gray-200 rounded animate-pulse w-1/4"></div>
                </div>
                <TableSkeleton rows={10} columns={4} columnWidths={["25%", "25%", "25%", "25%"]} />
            </div>
        );
    }

    if (!attribute) {
        return (
            <div className="flex h-full items-center justify-center bg-white text-gray-400 text-[16px]">
                {t("no_attributes")}
            </div>
        );
    }

    return (
        <div>
            {/* Values */}
            <AttributeValuesView
                key={`${attribute.attribute_id}-${attribute.is_hierarchical}`}
                attribute={attribute}
            />
        </div>
    );
}
