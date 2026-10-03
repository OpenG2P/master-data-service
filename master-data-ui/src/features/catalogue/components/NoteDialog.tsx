"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import Button from "@/components/Button";
import { ErrorBox, Field, Modal, isoToLocalInput, localInputToIso, textareaClass, inputClass } from "./ui";

export interface NoteDialogResult {
    note?: string;
    effective_from?: string;
}

interface NoteDialogProps {
    open: boolean;
    title: string;
    message?: string;
    noteLabel: string;
    noteRequired?: boolean;
    initialNote?: string | null;
    showEffectiveFrom?: boolean;
    initialEffectiveFrom?: string | null;
    effectiveFromHint?: string;
    confirmLabel: string;
    confirmVariant?: "primary" | "danger" | "warning";
    onConfirm: (result: NoteDialogResult) => Promise<void>;
    onClose: () => void;
}

/**
 * Asks for a note (change / decision note) and optionally an effective date, then runs `onConfirm`.
 * Backend errors from `onConfirm` are shown inside the dialog. Mount it only while open
 * (or change its `key`) so its fields start from the initial values.
 */
export default function NoteDialog({
    open,
    title,
    message,
    noteLabel,
    noteRequired = false,
    initialNote,
    showEffectiveFrom = false,
    initialEffectiveFrom,
    effectiveFromHint,
    confirmLabel,
    confirmVariant = "primary",
    onConfirm,
    onClose,
}: NoteDialogProps) {
    const t = useTranslations();
    const [note, setNote] = useState(initialNote ?? "");
    const [effective, setEffective] = useState(isoToLocalInput(initialEffectiveFrom));
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const submit = async () => {
        if (noteRequired && !note.trim()) {
            setError(t("cat_note_required"));
            return;
        }
        setBusy(true);
        setError(null);
        try {
            await onConfirm({
                note: note.trim() || undefined,
                effective_from: showEffectiveFrom ? localInputToIso(effective) : undefined,
            });
        } catch (e) {
            setError(e instanceof Error ? e.message : String(e));
        } finally {
            setBusy(false);
        }
    };

    return (
        <Modal open={open} title={title} onClose={busy ? () => undefined : onClose} zIndex="z-70">
            <form
                className="space-y-4"
                onSubmit={(e) => {
                    e.preventDefault();
                    void submit();
                }}
            >
                {message ? <p className="text-[15px] text-black/70">{message}</p> : null}
                <Field label={noteLabel} required={noteRequired}>
                    <textarea
                        value={note}
                        onChange={(e) => setNote(e.target.value)}
                        rows={3}
                        autoFocus
                        className={textareaClass}
                    />
                </Field>
                {showEffectiveFrom ? (
                    <Field label={t("cat_effective_from")} hint={effectiveFromHint ?? t("cat_effective_from_hint")}>
                        <input
                            type="datetime-local"
                            value={effective}
                            onChange={(e) => setEffective(e.target.value)}
                            className={inputClass}
                        />
                    </Field>
                ) : null}
                <ErrorBox message={error} />
                <div className="flex gap-4 w-full justify-end pt-2">
                    <Button variant="secondary" onClick={onClose} disabled={busy}>
                        {t("cancel")}
                    </Button>
                    <Button variant={confirmVariant} type="submit" loading={busy}>
                        {confirmLabel}
                    </Button>
                </div>
            </form>
        </Modal>
    );
}
