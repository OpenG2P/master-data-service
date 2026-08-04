export function SkeletonInput({ className = "" }: { className?: string }) {
  return <div className={`animate-pulse bg-gray-200 w-full h-[38px] rounded-[8px] ${className}`} />;
}

export function SkeletonLabel({ className = "" }: { className?: string }) {
  return <div className={`animate-pulse bg-gray-200 w-[80px] h-[12px] mb-2 rounded-[4px] ${className}`} />;
}

export function SkeletonTitle({ width = "220px", height = "28px", className = "" }: { width?: string; height?: string; className?: string }) {
  return <div className={`animate-pulse bg-gray-200 rounded-[8px] ${className}`} style={{ width, height }} />;
}
