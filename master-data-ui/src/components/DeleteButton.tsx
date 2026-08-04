import { ButtonHTMLAttributes, ReactNode } from "react";

interface DeleteButtonProps extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, "className"> {
  children: ReactNode;
  disabled?: boolean;
  title?: string;
}

export default function DeleteButton({
  children,
  disabled = false,
  title = "Delete",
  onClick,
  ...props
}: DeleteButtonProps) {
  return (
    <button
      type="button"
      className="inline-block text-[16px] font-medium px-4 py-2 rounded-[10px] cursor-pointer text-decoration-none leading-[1.2] border-none transition-colors duration-150 bg-[rgba(192,57,43,0.1)] text-[#c0392b] hover:bg-[rgba(192,57,43,0.2)] disabled:opacity-50 disabled:not-allowed"
      onClick={(e) => {
        e.stopPropagation();
        onClick?.(e);
      }}
      disabled={disabled}
      title={title}
      {...props}
    >
      {children}
    </button>
  );
}
