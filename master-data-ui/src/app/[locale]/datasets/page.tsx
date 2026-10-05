"use client";

import { Suspense } from "react";
import { AttributeListExplorer } from "@/features/attributes";

export default function DatasetsPage() {
    // The explorer reads ?q= and ?theme= (links from the home page).
    return (
        <Suspense>
            <AttributeListExplorer />
        </Suspense>
    );
}
