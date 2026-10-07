"use client";

import { useEffect, useId, type ReactNode } from "react";
import { X } from "lucide-react";
import { useTranslations } from "next-intl";

/** Input styling used by the existing value / node dialogs. */
export const inputClass =
    "h-10 w-full rounded border border-gray-300 bg-white px-3 text-[14px] text-black outline-none focus:border-[#EABB13] disabled:bg-gray-100 disabled:text-gray-500";
export const textareaClass =
    "w-full rounded border border-gray-300 bg-white px-3 py-2 text-[14px] text-black outline-none focus:border-[#EABB13]";
export const thClass =
    "text-left pb-3 pt-1 px-4 border-b border-gray-200 font-semibold text-[#ED7C22] text-[15px] tracking-wider";
export const tdClass = "py-2 px-4 align-middle text-[15px]";

export function formatDateTime(value?: string | null): string {
    if (!value) return "—";
    const d = new Date(value);
    if (Number.isNaN(d.getTime())) return value;
    return d.toLocaleString();
}

/**
 * A person recorded by the catalogue: `*_by` fields hold the stable user id (token `sub`),
 * `*_by_name` / `actor_name` the display name. Show the name; fall back to the id.
 */
export function personLabel(id?: string | null, name?: string | null): string {
    return (name && name.trim()) || id || "—";
}

export function formatDate(value?: string | null): string {
    if (!value) return "—";
    const d = new Date(value);
    if (Number.isNaN(d.getTime())) return value;
    return d.toLocaleDateString();
}

/** `<input type="datetime-local">` value → ISO string (local time), or undefined when empty. */
export function localInputToIso(value: string): string | undefined {
    if (!value) return undefined;
    const d = new Date(value);
    return Number.isNaN(d.getTime()) ? undefined : d.toISOString();
}

/** ISO string → `<input type="datetime-local">` value. */
export function isoToLocalInput(value?: string | null): string {
    if (!value) return "";
    const d = new Date(value);
    if (Number.isNaN(d.getTime())) return "";
    const pad = (n: number) => String(n).padStart(2, "0");
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

/** The label for the current locale, falling back to the default label. */
export function localizedLabel(
    fallback: string | null | undefined,
    i18n: Record<string, string> | null | undefined,
    locale: string,
): string {
    const fromLocale = i18n?.[locale] || i18n?.[locale.split("-")[0]];
    return fromLocale || fallback || "";
}

export function Field({
    label,
    required,
    hint,
    children,
    group = false,
}: {
    label: string;
    required?: boolean;
    hint?: ReactNode;
    children: ReactNode;
    /** Render as a div (for composite editors with several inputs / buttons). */
    group?: boolean;
}) {
    const Tag = group ? "div" : "label";
    return (
        <Tag className="block space-y-1.5">
            <span className="text-[12px] font-semibold uppercase tracking-wide text-black">
                {label}
                {required ? <span className="ml-1 text-red-500">*</span> : null}
            </span>
            {children}
            {hint ? <span className="block text-[12px] text-gray-500">{hint}</span> : null}
        </Tag>
    );
}

const STATUS_STYLES: Record<string, string> = {
    DRAFT: "bg-blue-50 text-blue-700 border-blue-200",
    SUBMITTED: "bg-amber-50 text-amber-700 border-amber-300",
    PUBLISHED: "bg-green-50 text-green-700 border-green-200",
    REJECTED: "bg-red-50 text-red-700 border-red-200",
    DISCARDED: "bg-gray-100 text-gray-600 border-gray-300",
    RETIRED: "bg-gray-100 text-gray-600 border-gray-300",
    ACTIVE: "bg-green-50 text-green-700 border-green-200",
    LATEST: "bg-[#f4bb1b]/20 text-black border-[#f4bb1b]",
    PENDING: "bg-purple-50 text-purple-700 border-purple-200",
    PUBLIC: "bg-emerald-50 text-emerald-700 border-emerald-300",
    PRIVATE: "bg-gray-100 text-gray-600 border-gray-300",
    AUTO: "bg-gray-100 text-gray-600 border-gray-300",
};

/** Small pill for a version / item status. Text is translated by the caller when needed. */
export function StatusBadge({
    status,
    label,
    title,
}: {
    status: string;
    label?: string;
    title?: string;
}) {
    const cls = STATUS_STYLES[status] ?? "bg-gray-100 text-gray-700 border-gray-300";
    return (
        <span
            title={title}
            className={`inline-flex items-center whitespace-nowrap rounded-full border px-2 py-0.5 text-[12px] font-semibold uppercase tracking-wide ${cls}`}
        >
            {label ?? status}
        </span>
    );
}

export type TabItem<K extends string> = { key: K; label: string; hidden?: boolean };

export function Tabs<K extends string>({
    tabs,
    active,
    onChange,
}: {
    tabs: TabItem<K>[];
    active: K;
    onChange: (key: K) => void;
}) {
    return (
        <div role="tablist" className="flex flex-wrap gap-1 border-b border-gray-200">
            {tabs
                .filter((tab) => !tab.hidden)
                .map((tab) => {
                    const isActive = tab.key === active;
                    return (
                        <button
                            key={tab.key}
                            type="button"
                            role="tab"
                            aria-selected={isActive}
                            onClick={() => onChange(tab.key)}
                            className={`-mb-px cursor-pointer border-b-[3px] px-4 py-2 text-[15px] font-medium transition-colors ${
                                isActive
                                    ? "border-[#f4bb1b] text-black"
                                    : "border-transparent text-gray-500 hover:text-black"
                            }`}
                        >
                            {tab.label}
                        </button>
                    );
                })}
        </div>
    );
}

/** Dialog shell matching the existing dialogs (yellow border, orange title). */
export function Modal({
    open,
    title,
    onClose,
    children,
    maxWidth = 600,
    zIndex = "z-60",
}: {
    open: boolean;
    title: string;
    onClose: () => void;
    children: ReactNode;
    maxWidth?: number;
    zIndex?: string;
}) {
    const t = useTranslations();
    const titleId = useId();

    useEffect(() => {
        if (!open) return;
        const onKeyDown = (e: KeyboardEvent) => {
            if (e.key === "Escape") onClose();
        };
        window.addEventListener("keydown", onKeyDown);
        return () => window.removeEventListener("keydown", onKeyDown);
    }, [open, onClose]);

    if (!open) return null;

    return (
        <div
            className={`fixed inset-0 ${zIndex} flex items-center justify-center bg-black/50 p-4`}
            role="presentation"
            onMouseDown={(e) => {
                if (e.target === e.currentTarget) onClose();
            }}
        >
            <div
                role="dialog"
                aria-modal="true"
                aria-labelledby={titleId}
                className="relative w-full bg-white rounded-[10px] shadow-lg max-h-[90vh] p-8 border-4 border-[#EABB13]"
                style={{ maxWidth: `${maxWidth}px` }}
                onClick={(e) => e.stopPropagation()}
            >
                <div className="flex items-center justify-between mb-6">
                    <h2 id={titleId} className="text-[22px] font-bold text-[#ED7C22]">
                        {title}
                    </h2>
                    <button
                        type="button"
                        onClick={onClose}
                        className="text-gray-500 hover:text-gray-800 transition-colors cursor-pointer"
                        aria-label={t("close")}
                    >
                        <X size={30} />
                    </button>
                </div>
                <div className="modal-scroll overflow-y-auto max-h-[calc(90vh-130px)] pr-2">{children}</div>
            </div>
        </div>
    );
}

/** Inline error box for backend errors (shown in place, not only as a toast). */
export function ErrorBox({ message }: { message?: string | null }) {
    if (!message) return null;
    return (
        <div className="rounded border border-red-200 bg-red-50 px-4 py-2 text-[14px] text-red-700" role="alert">
            {message}
        </div>
    );
}

export function Panel({ children, className = "" }: { children: ReactNode; className?: string }) {
    return <div className={`bg-white rounded-[10px] p-5 shadow-sm ${className}`}>{children}</div>;
}
