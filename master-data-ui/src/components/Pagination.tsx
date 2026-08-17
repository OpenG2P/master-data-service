"use client";

import Image from "next/image";

interface PaginationProps {
  page: number;
  pageSize: number;
  total: number;
  onPageChange: (page: number) => void;
}

export default function Pagination({
  page,
  pageSize,
  total,
  onPageChange,
}: PaginationProps) {
  const start = total === 0 ? 0 : (page - 1) * pageSize + 1;
  const end = Math.min(page * pageSize, total);
  const totalPages = Math.max(1, Math.ceil(total / pageSize) || 1);

  return (
    <div className="flex items-center gap-3">
      <span className="text-[14px] text-white">
        {start} - {end} of {total}
      </span>

      <button
        type="button"
        className="flex h-8 w-8 cursor-pointer items-center justify-center rounded bg-[#5A5A5A] disabled:cursor-not-allowed disabled:opacity-40"
        disabled={page <= 1}
        onClick={() => onPageChange(page - 1)}
        aria-label="Previous page"
      >
        <Image
          src="/arrow_back_01.png"
          width={14}
          height={14}
          alt=""
          className="block invert"
        />
      </button>

      <button
        type="button"
        className="flex h-8 w-8 cursor-pointer items-center justify-center rounded bg-[#5A5A5A] disabled:cursor-not-allowed disabled:opacity-40"
        disabled={page >= totalPages}
        onClick={() => onPageChange(page + 1)}
        aria-label="Next page"
      >
        <Image
          src="/arrow_next_01.png"
          width={14}
          height={14}
          alt=""
          className="block invert"
        />
      </button>
    </div>
  );
}
