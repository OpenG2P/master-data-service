import { ReactNode } from "react";

interface CardProps {
  children: ReactNode;
  className?: string;
  padding?: "none" | "sm" | "md" | "lg";
}

export default function Card({ children, className = "", padding = "md" }: CardProps) {
  const paddingClasses = {
    none: "",
    sm: "p-4",
    md: "p-6",
    lg: "p-8",
  };

  return (
    <div className={`bg-white rounded-[10px] shadow-[0_1px_2px_rgba(6,19,39,0.05)] ${paddingClasses[padding]} ${className}`}>
      {children}
    </div>
  );
}
