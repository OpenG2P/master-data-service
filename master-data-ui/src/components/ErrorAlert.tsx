import { ReactNode } from "react";

interface ErrorAlertProps {
  children: ReactNode;
  className?: string;
}

export default function ErrorAlert({ children, className = "" }: ErrorAlertProps) {
  return (
    <div className={`bg-[rgba(192,57,43,0.1)] text-[#c0392b] p-2.5 px-3.5 rounded mb-4 ${className}`}>
      {children}
    </div>
  );
}
