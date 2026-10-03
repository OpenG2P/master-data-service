"use client";

import { useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import { useCatalogueQuery } from "../api";
import type { ListDiffResponse, ListValue, VersionInfo } from "../types";
import { ErrorBox, StatusBadge, tdClass, thClass } from "./ui";

function show(value: unknown): string {
    if (value === null || value === undefined || value === "") return "—";
    if (typeof value === "string") return value;
    return JSON.stringify(value);
}

function ValueRows({ values }: { values: ListValue[] }) {
    const t = useTranslations();
    return (
        <table className="w-full table-fixed border-collapse">
            <thead>
                <tr>
                    <th className={thClass} style={{ width: "30%" }}>{t("value_code")}</th>
                    <th className={thClass} style={{ width: "35%" }}>{t("value_display")}</th>
                    <th className={thClass} style={{ width: "35%" }}>{t("cat_attributes")}</th>
                </tr>
            </thead>
            <tbody>
                {values.map((v, i) => (
                    <tr key={v.value_id} className={i % 2 ? "bg-white" : "bg-gray-50"}>
                        <td className={`${tdClass} font-mono truncate`}>{v.value_code}</td>
                        <td className={`${tdClass} truncate`}>{v.display || "—"}</td>
                        <td className={`${tdClass} truncate font-mono text-[13px]`} title={show(v.attributes)}>
                            {v.attributes && Object.keys(v.attributes).length ? show(v.attributes) : "—"}
                        </td>
                    </tr>
                ))}
            </tbody>
        </table>
    );
}

function Section({ title, count, status, children }: { title: string; count: number; status: string; children: React.ReactNode }) {
    if (count === 0) return null;
    return (
        <section className="space-y-2">
            <h3 className="flex items-center gap-2 text-[16px] font-semibold text-black">
                <StatusBadge status={status} label={title} />
                <span className="text-gray-500">({count})</span>
            </h3>
            {children}
        </section>
    );
}

/** Diff of a list between two versions (`get_list_diff`): added / changed / retired / reactivated + metadata. */
export default function ListDiffView({ listCode, versions }: { listCode: string; versions: VersionInfo[] }) {
    const t = useTranslations();
    const sorted = useMemo(() => [...versions].sort((a, b) => b.version_no - a.version_no), [versions]);
    const draft = sorted.find((v) => v.status === "DRAFT" || v.status === "SUBMITTED");
    const [to, setTo] = useState<string>(draft ? "draft" : "latest");
    const [from, setFrom] = useState<string>("");

    const { data, loading, error } = useCatalogueQuery<ListDiffResponse>("get_list_diff", {
        list_code: listCode,
        to_version: to === "draft" || to === "latest" ? to : Number(to),
        ...(from ? { from_version: Number(from) } : {}),
    });

    const selectCls =
        "h-9 rounded border border-gray-300 bg-white px-2 text-[14px] outline-none focus:border-[#EABB13]";
    const total = data
        ? data.added.length + data.changed.length + data.retired.length + data.reactivated.length +
          Object.keys(data.metadata_changes ?? {}).length
        : 0;

    return (
        <div className="space-y-5">
            <div className="flex flex-wrap items-center gap-4">
                <label className="flex items-center gap-2 text-[14px] font-semibold">
                    {t("cat_diff_from")}
                    <select value={from} onChange={(e) => setFrom(e.target.value)} className={selectCls}>
                        <option value="">{t("cat_diff_from_base")}</option>
                        {sorted
                            .filter((v) => v.status !== "DRAFT" && v.status !== "SUBMITTED")
                            .map((v) => (
                                <option key={v.version_no} value={String(v.version_no)}>
                                    v{v.version_no} · {t(`cat_status_${v.status}`)}
                                </option>
                            ))}
                    </select>
                </label>
                <label className="flex items-center gap-2 text-[14px] font-semibold">
                    {t("cat_diff_to")}
                    <select value={to} onChange={(e) => setTo(e.target.value)} className={selectCls}>
                        <option value="latest">{t("cat_version_latest")}</option>
                        {draft ? <option value="draft">{t("cat_version_draft_no", { no: draft.version_no, status: t(`cat_status_${draft.status}`) })}</option> : null}
                        {sorted
                            .filter((v) => v.version_no !== draft?.version_no)
                            .map((v) => (
                                <option key={v.version_no} value={String(v.version_no)}>
                                    v{v.version_no} · {t(`cat_status_${v.status}`)}
                                </option>
                            ))}
                    </select>
                </label>
                {data ? (
                    <span className="text-[14px] text-gray-600">
                        {t("cat_diff_between", { from: data.from_version ?? "—", to: data.to_version })}
                    </span>
                ) : null}
            </div>

            <ErrorBox message={error} />
            {loading ? <p className="text-[14px] text-gray-500">{t("loading")}</p> : null}

            {data && !loading ? (
                total === 0 ? (
                    <p className="text-[14px] text-gray-500">{t("cat_diff_none")}</p>
                ) : (
                    <div className="space-y-6">
                        {Object.keys(data.metadata_changes ?? {}).length > 0 ? (
                            <section className="space-y-2">
                                <h3 className="text-[16px] font-semibold text-black">{t("cat_diff_metadata")}</h3>
                                <table className="w-full table-fixed border-collapse">
                                    <thead>
                                        <tr>
                                            <th className={thClass} style={{ width: "20%" }}>{t("cat_field")}</th>
                                            <th className={thClass} style={{ width: "40%" }}>{t("cat_before")}</th>
                                            <th className={thClass} style={{ width: "40%" }}>{t("cat_after")}</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {Object.entries(data.metadata_changes).map(([field, change], i) => (
                                            <tr key={field} className={i % 2 ? "bg-white" : "bg-gray-50"}>
                                                <td className={`${tdClass} font-mono`}>{field}</td>
                                                <td className={`${tdClass} break-all font-mono text-[13px] text-red-700`}>{show(change.before)}</td>
                                                <td className={`${tdClass} break-all font-mono text-[13px] text-green-700`}>{show(change.after)}</td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            </section>
                        ) : null}

                        <Section title={t("cat_diff_added")} count={data.added.length} status="ACTIVE">
                            <ValueRows values={data.added} />
                        </Section>

                        <Section title={t("cat_diff_changed")} count={data.changed.length} status="SUBMITTED">
                            <table className="w-full table-fixed border-collapse">
                                <thead>
                                    <tr>
                                        <th className={thClass} style={{ width: "20%" }}>{t("value_code")}</th>
                                        <th className={thClass} style={{ width: "20%" }}>{t("cat_field")}</th>
                                        <th className={thClass} style={{ width: "30%" }}>{t("cat_before")}</th>
                                        <th className={thClass} style={{ width: "30%" }}>{t("cat_after")}</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {data.changed.flatMap((c, i) =>
                                        Object.entries(c.changes).map(([field, ch], j) => (
                                            <tr key={`${c.value_id}-${field}`} className={i % 2 ? "bg-white" : "bg-gray-50"}>
                                                <td className={`${tdClass} font-mono truncate`}>{j === 0 ? c.value_code : ""}</td>
                                                <td className={`${tdClass} font-mono`}>{field}</td>
                                                <td className={`${tdClass} break-all font-mono text-[13px] text-red-700`}>{show(ch.before)}</td>
                                                <td className={`${tdClass} break-all font-mono text-[13px] text-green-700`}>{show(ch.after)}</td>
                                            </tr>
                                        )),
                                    )}
                                </tbody>
                            </table>
                        </Section>

                        <Section title={t("cat_diff_retired")} count={data.retired.length} status="RETIRED">
                            <ValueRows values={data.retired} />
                        </Section>

                        <Section title={t("cat_diff_reactivated")} count={data.reactivated.length} status="PUBLISHED">
                            <ValueRows values={data.reactivated} />
                        </Section>
                    </div>
                )
            ) : null}
        </div>
    );
}
