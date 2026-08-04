"use client";

import { X } from 'lucide-react';
import { useTranslations } from 'next-intl';

interface ConfirmModalProps {
  title?: string;
  warningText?: string;
  confirming?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

export default function ConfirmModal({
  title,
  warningText,
  confirming,
  onConfirm,
  onCancel,
}: ConfirmModalProps) {
  const t = useTranslations();

  return (
    <div className="fixed inset-0 bg-black/50 z-100 flex items-center justify-center p-4">
      <div className="relative w-full max-w-150 bg-white rounded-[10px] shadow-lg flex flex-col items-center p-8 border-4 border-[#dc3545]">
        <button
          onClick={onCancel}
          className="absolute top-4 right-4 text-gray-400 hover:text-gray-600 transition-colors cursor-pointer"
        >
          <X size={30} />
        </button>

        <div className="mb-6 mt-4">
          <div className="w-20 h-20 bg-gray-100 rounded-full flex items-center justify-center">
            <div className="w-14 h-14 bg-[#dc3545] rounded-full flex items-center justify-center">
              <span className="text-white text-[32px] font-bold">!</span>
            </div>
          </div>
        </div>

        <h2 className="text-[22px] font-bold text-black mb-2 text-center">{title || t("confirm")}</h2>
        <p className="text-black/70 text-[18px] text-center mb-8 px-4">
          {warningText}
        </p>

        <div className="flex gap-4 w-full justify-center">
          <button
            onClick={onCancel}
            className="px-8 py-2 bg-black text-white font-semibold rounded-[10px] hover:bg-black/80 transition-colors text-[16px] cursor-pointer"
            disabled={confirming}
          >
            {t("cancel")}
          </button>
          <button
            onClick={onConfirm}
            className="px-8 py-2 bg-[#dc3545] text-white font-semibold rounded-[10px] hover:bg-[#dc3545]/80 transition-colors text-[16px] flex items-center gap-2 cursor-pointer"
            disabled={confirming}
          >
            {confirming && (
              <svg
                className="animate-spin h-4 w-4"
                xmlns="http://www.w3.org/2000/svg"
                fill="none"
                viewBox="0 0 24 24"
              >
                <circle
                  className="opacity-25"
                  cx="12"
                  cy="12"
                  r="10"
                  stroke="currentColor"
                  strokeWidth="4"
                ></circle>
                <path
                  className="opacity-75"
                  fill="currentColor"
                  d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                ></path>
              </svg>
            )}
            {t("delete")}
          </button>
        </div>
      </div>
    </div>
  );
}
