"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { toast } from "react-toastify";
import AddButton from "@/components/AddButton";
import Button from "@/components/Button";
import Can from "@/components/Can";
import ConfirmDialog from "@/components/ConfirmDialog";
import TableSkeleton from "@/components/TableSkeleton";
import { useRbac } from "@/context/RbacContext";
import { errorMessage, useCatalogueApi, useCatalogueQuery } from "@/features/catalogue/api";
import { useIsMaker } from "@/features/catalogue/hooks";
import {
    ErrorBox,
    Field,
    Modal,
    Panel,
    StatusBadge,
    formatDateTime,
    inputClass,
    personLabel,
    tdClass,
    textareaClass,
    thClass,
} from "@/features/catalogue/components/ui";
import type {
    GetGeoVersionsResponse,
    GetListsResponse,
    GetReleaseResponse,
    GetReleasesResponse,
} from "@/features/catalogue/types";
import ReleaseMembersEditor from "./ReleaseMembersEditor";

const RELEASE_ACTIONS = {
    edit: "referenceData:edit",
    delete: "referenceData:delete",
    publish: "referenceData:publish",
};

const EMPTY = {};
const ALL_LISTS = { include_unpublished: true };

function CreateReleaseDialog({ onClose, onCreated }: { onClose: () => void; onCreated: (code: string) => void }) {
    const t = useTranslations();
    const call = useCatalogueApi();
    const [code, setCode] = useState("");
    const [title, setTitle] = useState("");
    const [note, setNote] = useState("");
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const submit = async () => {
        if (!code.trim()) {
            setError(t("cat_release_code_required"));
            return;
        }
        setBusy(true);
        setError(null);
        try {
            await call<GetReleaseResponse>("create_release", {
                release_code: code.trim(),
                title: title.trim() || undefined,
                note: note.trim() || undefined,
            });
            toast.success(t("cat_release_created"));
            onCreated(code.trim());
        } catch (e) {
            setError(errorMessage(e));
        } finally {
            setBusy(false);
        }
    };

    return (
        <Modal open title={t("cat_create_release")} onClose={onClose}>
            <form
                className="space-y-4"
                onSubmit={(e) => {
                    e.preventDefault();
                    void submit();
                }}
            >
                <Field label={t("cat_release_code")} required hint={t("cat_release_code_hint")}>
                    <input value={code} onChange={(e) => setCode(e.target.value)} autoFocus className={`${inputClass} font-mono`} />
                </Field>
                <Field label={t("cat_title")}>
                    <input value={title} onChange={(e) => setTitle(e.target.value)} className={inputClass} />
                </Field>
                <Field label={t("cat_note")}>
                    <textarea value={note} onChange={(e) => setNote(e.target.value)} rows={3} className={textareaClass} />
                </Field>
                <ErrorBox message={error} />
                <div className="flex justify-end gap-3">
                    <Button variant="secondary" onClick={onClose} disabled={busy}>
                        {t("cancel")}
                    </Button>
                    <Button type="submit" loading={busy}>
                        {t("cat_create_release")}
                    </Button>
                </div>
            </form>
        </Modal>
    );
}

function ReleaseDetail({ code, onChanged, onDeleted }: { code: string; onChanged: () => void; onDeleted: () => void }) {
    const t = useTranslations();
    const call = useCatalogueApi();
    const { can } = useRbac();
    const isMaker = useIsMaker();
    const [editing, setEditing] = useState(false);
    const [confirm, setConfirm] = useState<"publish" | "delete" | null>(null);
    const [busy, setBusy] = useState(false);

    const { data, loading, error, reload } = useCatalogueQuery<GetReleaseResponse>("get_release", { release_code: code });
    const lists = useCatalogueQuery<GetListsResponse>("get_lists", editing ? ALL_LISTS : null);
    const geo = useCatalogueQuery<GetGeoVersionsResponse>("get_geo_versions", EMPTY);

    if (!data) {
        return (
            <Panel>
                <ErrorBox message={error} />
                {loading ? <p className="text-[14px] text-gray-500">{t("loading")}</p> : null}
            </Panel>
        );
    }

    const { release, members } = data;
    const isDraft = release.status === "DRAFT";
    // The backend excludes both the creator and whoever last set the members (by user id).
    const creatorIsMe = isMaker({
        version_no: 0,
        status: release.status,
        created_by: release.created_by,
        updated_by: release.members_set_by,
    });

    const act = async (kind: "publish" | "delete") => {
        setBusy(true);
        try {
            if (kind === "publish") {
                await call("publish_release", { release_code: code });
                toast.success(t("cat_release_published"));
                reload();
                onChanged();
            } else {
                await call("delete_release", { release_code: code });
                toast.success(t("cat_release_deleted"));
                onDeleted();
            }
        } catch (e) {
            toast.error(errorMessage(e));
        } finally {
            setBusy(false);
            setConfirm(null);
        }
    };

    return (
        <Panel className="space-y-4">
            <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="space-y-1">
                    <h2 className="flex items-center gap-2 text-[20px] font-semibold text-black">
                        <span className="font-mono">{release.release_code}</span>
                        <StatusBadge status={release.status} label={t(`cat_status_${release.status}`)} />
                    </h2>
                    {release.title ? <p className="text-[15px] text-black">{release.title}</p> : null}
                    {release.note ? <p className="text-[13px] text-gray-600">{release.note}</p> : null}
                    <p className="text-[13px] text-gray-500">
                        {t("cat_created_by_at", {
                            by: personLabel(release.created_by, release.created_by_name),
                            at: formatDateTime(release.created_at),
                        })}
                        {release.published_at
                            ? ` · ${t("cat_published_by_at", {
                                  by: personLabel(release.published_by, release.published_by_name),
                                  at: formatDateTime(release.published_at),
                              })}`
                            : ""}
                    </p>
                </div>
                {isDraft ? (
                    <div className="flex flex-wrap gap-2">
                        {!editing && can(RELEASE_ACTIONS.edit) ? (
                            <Button variant="secondary" onClick={() => setEditing(true)}>
                                {t("cat_set_members")}
                            </Button>
                        ) : null}
                        {can(RELEASE_ACTIONS.publish) && !creatorIsMe ? (
                            <Button onClick={() => setConfirm("publish")} disabled={editing}>
                                {t("cat_publish")}
                            </Button>
                        ) : null}
                        {can(RELEASE_ACTIONS.delete) ? (
                            <Button variant="danger" onClick={() => setConfirm("delete")} disabled={editing}>
                                {t("delete")}
                            </Button>
                        ) : null}
                    </div>
                ) : null}
            </div>
            {isDraft && can(RELEASE_ACTIONS.publish) && creatorIsMe ? (
                <p className="rounded bg-amber-50 px-3 py-2 text-[13px] text-amber-800">{t("cat_release_maker_hint")}</p>
            ) : null}

            {editing ? (
                <ReleaseMembersEditor
                    members={members}
                    geoVersionNo={release.geo_version_no}
                    lists={lists.data?.lists ?? []}
                    geoVersions={geo.data?.versions ?? []}
                    onCancel={() => setEditing(false)}
                    onSave={async (rows, geoVersionNo) => {
                        await call("set_release_members", {
                            release_code: code,
                            members: rows,
                            geo_version_no: geoVersionNo,
                            replace: true,
                        });
                        toast.success(t("cat_release_members_saved"));
                        setEditing(false);
                        reload();
                        onChanged();
                    }}
                />
            ) : (
                <>
                    <p className="text-[14px]">
                        <span className="font-semibold">{t("cat_geo_version")}:</span>{" "}
                        {release.geo_version_no != null ? `v${release.geo_version_no}` : t("cat_no_geo_pin")}
                    </p>
                    <table className="w-full table-fixed border-collapse">
                        <thead>
                            <tr>
                                <th className={thClass}>{t("cat_list")}</th>
                                <th className={thClass}>{t("cat_version")}</th>
                            </tr>
                        </thead>
                        <tbody>
                            {members.length === 0 ? (
                                <tr>
                                    <td colSpan={2} className="py-6 text-center text-[14px] text-gray-500">
                                        {t("cat_release_no_members")}
                                    </td>
                                </tr>
                            ) : (
                                members.map((m, i) => (
                                    <tr key={m.list_code} className={i % 2 ? "bg-white" : "bg-gray-50"}>
                                        <td className={`${tdClass} font-mono`}>{m.list_code}</td>
                                        <td className={tdClass}>v{m.version_no}</td>
                                    </tr>
                                ))
                            )}
                        </tbody>
                    </table>
                </>
            )}

            <ConfirmDialog
                open={confirm !== null}
                title={confirm === "publish" ? t("cat_publish_release_title") : t("cat_delete_release_title")}
                message={
                    confirm === "publish"
                        ? t("cat_publish_release_message", { code })
                        : t("cat_delete_release_message", { code })
                }
                confirmLabel={confirm === "publish" ? t("cat_publish") : t("delete")}
                danger={confirm === "delete"}
                confirmingLabel={confirm === "publish" ? t("cat_publishing") : undefined}
                confirming={busy}
                onConfirm={() => confirm && void act(confirm)}
                onClose={() => setConfirm(null)}
            />
        </Panel>
    );
}

/**
 * Catalogue releases: named, immutable sets of list versions plus one geography version, for
 * consumers that pin everything at once. Create, set members, publish, delete (draft only).
 */
export default function ReleasesExplorer() {
    const t = useTranslations();
    const [creating, setCreating] = useState(false);
    const [selected, setSelected] = useState<string | null>(null);
    const { data, loading, error, reload } = useCatalogueQuery<GetReleasesResponse>("get_releases", EMPTY);
    const releases = data?.releases ?? [];

    return (
        <div className="space-y-4">
            <div className="flex items-center justify-between gap-4">
                <div>
                    <h1 className="font-semibold text-[24px] text-black">{t("releases")}</h1>
                    <p className="text-[14px] text-gray-600">{t("cat_releases_hint")}</p>
                </div>
                <Can action={RELEASE_ACTIONS.edit}>
                    <AddButton onClick={() => setCreating(true)} label={t("cat_create_release")} />
                </Can>
            </div>

            <ErrorBox message={error} />

            {loading && !data ? (
                <TableSkeleton rows={6} columns={6} />
            ) : (
                <div className="bg-white rounded-[10px] pt-4 pb-3 shadow-sm overflow-auto">
                    <table className="w-full min-w-[900px] border-collapse">
                        <thead>
                            <tr>
                                <th className={thClass}>{t("cat_release_code")}</th>
                                <th className={thClass}>{t("cat_title")}</th>
                                <th className={thClass}>{t("col_status")}</th>
                                <th className={thClass}>{t("cat_members")}</th>
                                <th className={thClass}>{t("cat_geo_version")}</th>
                                <th className={thClass}>{t("cat_published")}</th>
                            </tr>
                        </thead>
                        <tbody>
                            {releases.length === 0 ? (
                                <tr>
                                    <td colSpan={6} className="py-8 text-center text-gray-500">
                                        {t("cat_no_releases")}
                                    </td>
                                </tr>
                            ) : (
                                releases.map((r, i) => (
                                    <tr
                                        key={r.release_code}
                                        onClick={() => setSelected(r.release_code)}
                                        className={`cursor-pointer ${selected === r.release_code ? "bg-[#f4bb1b]/15" : i % 2 ? "bg-white" : "bg-gray-50"} hover:bg-gray-100`}
                                    >
                                        <td className={`${tdClass} font-mono`}>{r.release_code}</td>
                                        <td className={tdClass}>{r.title || "—"}</td>
                                        <td className={tdClass}>
                                            <StatusBadge status={r.status} label={t(`cat_status_${r.status}`)} />
                                        </td>
                                        <td className={tdClass}>{r.member_count}</td>
                                        <td className={tdClass}>{r.geo_version_no != null ? `v${r.geo_version_no}` : "—"}</td>
                                        <td className={`${tdClass} text-[13px]`}>
                                            {r.published_at ? `${formatDateTime(r.published_at)} · ${personLabel(r.published_by, r.published_by_name)}` : "—"}
                                        </td>
                                    </tr>
                                ))
                            )}
                        </tbody>
                    </table>
                </div>
            )}

            {selected ? (
                <ReleaseDetail
                    key={selected}
                    code={selected}
                    onChanged={reload}
                    onDeleted={() => {
                        setSelected(null);
                        reload();
                    }}
                />
            ) : null}

            {creating ? (
                <CreateReleaseDialog
                    onClose={() => setCreating(false)}
                    onCreated={(code) => {
                        setCreating(false);
                        setSelected(code);
                        reload();
                    }}
                />
            ) : null}
        </div>
    );
}
