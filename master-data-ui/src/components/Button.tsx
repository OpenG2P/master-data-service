"use client";

interface ButtonProps {
  children: React.ReactNode;
  type?: "button" | "submit" | "reset";
  variant?: "primary" | "secondary" | "danger";
  disabled?: boolean;
  loading?: boolean;
  onClick?: () => void;
  className?: string;
}

export default function Button({
  children,
  type = "button",
  variant = "primary",
  disabled = false,
  loading = false,
  onClick,
  className = "",
}: ButtonProps) {
  const baseStyles = "inline-flex items-center justify-center text-[16px] font-medium px-4 py-2 rounded-[10px] cursor-pointer text-decoration-none leading-[1.2] border-none transition-colors duration-150 disabled:opacity-50 disabled:not-allowed relative";

  const variantStyles = {
    primary: "bg-black text-white hover:bg-gray-800",
    secondary: "bg-[#e1e1e1] text-black/50 hover:bg-[#d1d1d1]",
    danger: "bg-red-500 text-white hover:bg-red-600",
  };

  return (
    <button
      type={type}
      disabled={disabled || loading}
      onClick={onClick}
      className={`${baseStyles} ${variantStyles[variant]} ${className}`}
    >
      {loading && (
        <svg
          className="animate-spin h-4 w-4 mr-2"
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
      {children}
    </button>
  );
}
