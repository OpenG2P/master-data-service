"use client";

interface InputFieldProps {
  label?: string;
  value: string | number;
  onChange: (value: string) => void;
  placeholder?: string;
  type?: string;
  disabled?: boolean;
  min?: number;
  max?: number;
  className?: string;
  required?: boolean;
}

export default function InputField({
  label,
  value,
  onChange,
  placeholder,
  type = "text",
  disabled = false,
  min,
  max,
  className = "",
  required = false,
}: InputFieldProps) {
  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const nextValue = e.target.value;
    if (nextValue !== "" && min !== undefined && Number(nextValue) < min) {
      return;
    }
    if (nextValue !== "" && max !== undefined && Number(nextValue) > max) {
      return;
    }
    onChange(nextValue);
  };

  return (
    <div className={`flex flex-col gap-1.5 ${className}`}>
      {label && (
        <label className="text-[16px] font-medium text-black">
          {label}
          {required && <span className="text-red-500 ml-1">*</span>}
        </label>
      )}
      <input
        type={type}
        value={value}
        placeholder={placeholder}
        disabled={disabled}
        min={min}
        max={max}
        required={required}
        onChange={handleChange}
        className={`text-[16px] p-2 border border-[#ED7C22] rounded-[10px] bg-white text-black focus:outline-none disabled:bg-gray-100 disabled:text-gray-500 disabled:cursor-not-allowed ${disabled ? 'bg-gray-100 text-gray-500 cursor-not-allowed' : ''}`}
      />
    </div>
  );
}
