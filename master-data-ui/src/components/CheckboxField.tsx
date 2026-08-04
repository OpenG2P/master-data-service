"use client";

interface CheckboxFieldProps {
  label?: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
  disabled?: boolean;
  className?: string;
}

export default function CheckboxField({
  label,
  checked,
  onChange,
  disabled = false,
  className = "",
}: CheckboxFieldProps) {
  return (
    <div className={`flex flex-col gap-2 ${className}`}>
      <label
        className={`text-[16px] font-medium text-black flex items-center gap-2 ${disabled ? "cursor-not-allowed opacity-50" : "cursor-pointer"
          }`}
      >
        <span className="relative inline-flex shrink-0">
          <input
            type="checkbox"
            className="peer absolute inset-0 w-5 h-5 opacity-0 cursor-[inherit]"
            checked={checked}
            disabled={disabled}
            onChange={(e) => onChange(e.target.checked)}
          />
          <span
            className="w-5 h-5 rounded border-2 flex items-center justify-center transition-colors"
            style={{
              borderColor: "#ED7C22",
              backgroundColor: checked ? "#EABB13" : "white",
            }}
          >
            {checked && (
              <svg
                viewBox="0 0 16 16"
                fill="none"
                className="w-4 h-4"
                aria-hidden="true"
              >
                <path
                  d="M2.5 8L6 11.5L13.5 4"
                  stroke="white"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
            )}
          </span>
        </span>
        {label}
      </label>
    </div>
  );
}
