"use client";

import { useParams } from "next/navigation";
import { AttributeDetail } from "@/features/attributes";

export default function DatasetPage() {
    const { attributeId: rawId } = useParams<{ attributeId: string }>();
    const attributeId = decodeURIComponent(rawId ?? "");

    return <AttributeDetail attributeId={attributeId} />;
}
