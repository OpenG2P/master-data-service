interface StatusBadgeProps {
  active?: boolean;
  activeLabel?: string;
  inactiveLabel?: string;
}

export default function StatusBadge({
  active,
  activeLabel = "Active",
  inactiveLabel = "Inactive",
}: StatusBadgeProps) {
  return (
    <span
      className={`inline-block px-4 py-2 rounded-[10px] text-[16px] font-medium ${active !== false ? "bg-[rgba(39,174,96,0.12)] text-[#27ae60]" : "bg-[rgba(196,196,196,0.3)] text-gray-600"}`}
    >
      {active !== false ? activeLabel : inactiveLabel}
    </span>
  );
}
