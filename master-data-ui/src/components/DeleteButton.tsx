import { ButtonHTMLAttributes, ReactNode } from "react";

interface DeleteButtonProps extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, "className"> {
  children: ReactNode;
  disabled?: boolean;
  loading?: boolean;
  title?: string;
}

export default function DeleteButton({
  children,
  disabled = false,
  loading = false,
  title = "Delete",
  onClick,
  ...props
}: DeleteButtonProps) {
  return (
    <button
      type="button"
      className="inline-flex items-center justify-center text-[16px] font-medium px-4 py-2 rounded-[10px] cursor-pointer text-decoration-none leading-[1.2] border-none transition-colors duration-150 bg-[rgba(192,57,43,0.1)] text-[#c0392b] hover:bg-[rgba(192,57,43,0.2)] disabled:opacity-50 disabled:not-allowed"
      onClick={(e) => {
        e.stopPropagation();
        onClick?.(e);
      }}
      disabled={disabled || loading}
      title={title}
      {...props}
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
      {loading ? "Deleting" : children}
    </button>
  );
}
