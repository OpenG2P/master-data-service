import { ButtonHTMLAttributes, ReactNode } from "react";

interface EditButtonProps extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, "className"> {
  children: ReactNode;
  disabled?: boolean;
  title?: string;
}

export default function EditButton({
  children,
  disabled = false,
  title = "Edit",
  onClick,
  ...props
}: EditButtonProps) {
  return (
    <button
      type="button"
      className="inline-block text-[16px] font-medium px-4 py-2 rounded-[10px] cursor-pointer text-decoration-none leading-[1.2] border-none transition-colors duration-150 bg-[rgba(0,0,0,0.05)] text-black hover:bg-[rgba(0,0,0,0.1)] disabled:opacity-50 disabled:not-allowed"
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
