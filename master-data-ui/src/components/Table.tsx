"use client";

import { ReactNode } from "react";

interface Column<T> {
  key: string;
  header: string;
  render: (item: T) => ReactNode;
}

interface TableProps<T> {
  columns: Column<T>[];
  data: T[];
  onRowClick?: (item: T) => void;
  emptyMessage?: string;
}

export default function Table<T>({
  columns,
  data,
  onRowClick,
  emptyMessage = "No records found.",
}: TableProps<T>) {
  return (
    <table className="w-full border-collapse bg-white table-fixed">
      <thead>
        <tr>
          {columns.map((column) => (
            <th
              key={column.key}
              className="text-left pb-3 px-9 border-b border-gray-200 font-semibold text-[#ED7C22] text-[16px] tracking-wider"
              style={{ width: `${100 / columns.length}%` }}
            >
              <div className="truncate" title={column.header}>
                {column.header}
              </div>
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {data.length === 0 ? (
          <tr>
            <td colSpan={columns.length} className="text-center py-10 px-4 text-gray-600">
              <p className="text-gray-600">{emptyMessage}</p>
            </td>
          </tr>
        ) : (
          data.map((item, index) => (
            <tr
              key={index}
              className={`cursor-pointer transition-colors duration-150 ${index % 2 === 1 ? 'bg-white' : 'bg-gray-50'} hover:bg-gray-100`}
              onClick={() => onRowClick?.(item)}
            >
              {columns.map((column) => (
                <td key={column.key} className="py-4 px-9 align-middle">
                  <div className="truncate" title={String(column.render(item))}>
                    {column.render(item)}
                  </div>
                </td>
              ))}
            </tr>
          ))
        )}
      </tbody>
    </table>
  );
}
