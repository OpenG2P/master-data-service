import { ReactNode } from "react";

interface FormActionsProps {
  children: ReactNode;
  withBorder?: boolean;
}

export default function FormActions({ children, withBorder = false }: FormActionsProps) {
  return (
    <div className={`flex gap-3 justify-end mt-5 ${withBorder ? "pt-4 border-t border-gray-100" : ""}`}>
      {children}
    </div>
  );
}
