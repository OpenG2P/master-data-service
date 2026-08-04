"use client";

import { useTranslations } from "next-intl";
import DataTablePanel, {
  type DataTableColumn,
} from "@/components/DataTablePanel";

type ReferenceRow = {
  id: string;
  name: string;
  status: string;
  actions: string;
};

const SAMPLE_REFERENCE: ReferenceRow[] = [];

export default function ReferenceDataPage() {
  const t = useTranslations();

  const columns: DataTableColumn<ReferenceRow>[] = [
    {
      key: "no",
      header: t("col_no"),
      render: (_row, index) => String(index + 1).padStart(2, "0"),
    },
    { key: "name", header: t("col_name") },
    { key: "status", header: t("col_status") },
    { key: "actions", header: t("col_actions") },
  ];

  return (
    <DataTablePanel
      tableLabel={t("reference_data")}
      columns={columns}
      data={SAMPLE_REFERENCE}
      searchKeys={["name"]}
    />
  );
}
