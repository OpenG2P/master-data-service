import { ButtonHTMLAttributes, ReactNode } from "react";

interface SecondaryButtonProps extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, "className"> {
  children: ReactNode;
}

export default function SecondaryButton({ children, disabled = false, onClick, ...props }: SecondaryButtonProps) {
  return (
    <button
      type="button"
      className="inline-block text-[16px] font-medium px-4 py-2 border border-[#ED7C22] rounded-[10px] cursor-pointer text-decoration-none leading-[1.2] transition-colors duration-150 bg-transparent text-black hover:bg-gray-100 disabled:opacity-50 disabled:not-allowed"
      disabled={disabled}
      onClick={onClick}
      {...props}
    >
      {children}
    </button>
  );
}
