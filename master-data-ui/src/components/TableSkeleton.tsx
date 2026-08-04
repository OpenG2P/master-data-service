"use client";

type TableSkeletonProps = {
  rows?: number;
  columns?: number;
  headers?: string[];
};

export default function TableSkeleton({
  rows = 5,
  columns = 4,
  headers,
}: TableSkeletonProps) {
  const colCount = headers ? headers.length : columns;

  // Generate slightly different widths for skeleton blocks to make them look more natural
  const getWidth = (colIndex: number) => {
    if (colIndex === colCount - 1) return "60px"; // Status column
    const widths = ["120px", "240px", "180px", "150px"];
    return widths[colIndex % widths.length];
  };

  return (
    <div className="overflow-x-auto" aria-hidden>
      <table className="w-full border-collapse bg-white">
        <thead>
          <tr>
            {headers ? (
              headers.map((h, i) => (
                <th key={i} className="text-left pb-3 px-9 border-b border-gray-200 font-semibold text-[#ED7C22] text-[16px] tracking-wider">
                  {h}
                </th>
              ))
            ) : (
              Array.from({ length: colCount }).map((_, i) => (
                <th key={i} className="text-left pb-3 px-9 border-b border-gray-200">
                  <div className="h-5 w-24 bg-gray-200 rounded animate-pulse" />
                </th>
              ))
            )}
          </tr>
        </thead>
        <tbody>
          {Array.from({ length: rows }).map((_, rowIndex) => (
            <tr key={rowIndex} className={rowIndex % 2 === 1 ? 'bg-white' : 'bg-gray-50'}>
              {Array.from({ length: colCount }).map((__, colIndex) => (
                <td key={colIndex} className="py-4 px-9 align-middle">
                  <div
                    className="h-3.5 rounded-md bg-gray-200 animate-pulse"
                    style={{ width: getWidth(colIndex) }}
                  />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
