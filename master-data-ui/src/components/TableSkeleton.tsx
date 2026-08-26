"use client";

type TableSkeletonProps = {
  rows?: number;
  columns?: number;
  columnWidths?: string[];
  headerRow?: boolean;
};

export default function TableSkeleton({ 
  rows = 10, 
  columns = 4,
  columnWidths,
  headerRow = true
}: TableSkeletonProps) {
  const getWidth = (idx: number) => {
    if (columnWidths && columnWidths[idx]) {
      return columnWidths[idx];
    }
    return `${100 / columns}%`;
  };

  return (
    <div className="bg-white rounded-[10px] py-6 shadow-sm">
      <div className="overflow-auto">
        <table className="w-full border-collapse bg-white table-fixed">
          {headerRow && (
            <thead>
              <tr>
                {Array.from({ length: columns }).map((_, idx) => (
                  <th
                    key={idx}
                    className="text-left pb-3 px-9 border-b border-gray-200"
                    style={{ width: getWidth(idx) }}
                  >
                    <div className="h-4 bg-gray-200 rounded animate-pulse"></div>
                  </th>
                ))}
              </tr>
            </thead>
          )}
          <tbody>
            {Array.from({ length: rows }).map((_, rowIdx) => (
              <tr key={rowIdx} className={rowIdx % 2 === 1 ? 'bg-gray-50' : 'bg-white'}>
                {Array.from({ length: columns }).map((_, colIdx) => (
                  <td key={colIdx} className="py-2 px-9 align-middle">
                    <div className="h-4 bg-gray-200 rounded animate-pulse"></div>
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
