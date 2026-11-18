"use client";

import React from "react";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { EmptyState } from "@/components/shared/empty-state";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

export interface ColumnDef<T> {
  header: string;
  accessorKey?: keyof T;
  cell?: (row: T) => React.ReactNode;
  className?: string;
  headerClassName?: string;
}

interface DataTableProps<T> {
  columns: ColumnDef<T>[];
  data: T[];
  isLoading?: boolean;
  keyExtractor: (row: T, index: number) => string | number;
  emptyTitle?: string;
  emptyDescription?: string;
  onRowClick?: (row: T) => void;
  className?: string;
}

export function DataTable<T>({
  columns,
  data,
  isLoading = false,
  keyExtractor,
  emptyTitle = "No records found",
  emptyDescription = "There are no records to display at this time.",
  onRowClick,
  className,
}: DataTableProps<T>) {
  if (isLoading) {
    return (
      <div className={cn("rounded-xl border border-slate-200 bg-white overflow-hidden shadow-sm", className)}>
        <Table>
          <TableHeader>
            <TableRow className="bg-slate-50/75 hover:bg-slate-50/75">
              {columns.map((col, idx) => (
                <TableHead key={idx} className={cn("text-xs font-semibold text-slate-600", col.headerClassName)}>
                  {col.header}
                </TableHead>
              ))}
            </TableRow>
          </TableHeader>
          <TableBody>
            {Array.from({ length: 5 }).map((_, rowIdx) => (
              <TableRow key={rowIdx}>
                {columns.map((_, colIdx) => (
                  <TableCell key={colIdx} className="py-3.5">
                    <Skeleton className="h-4 w-full max-w-[140px]" />
                  </TableCell>
                ))}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    );
  }

  if (data.length === 0) {
    return (
      <EmptyState
        title={emptyTitle}
        description={emptyDescription}
        className={className}
      />
    );
  }

  return (
    <div className={cn("rounded-xl border border-slate-200 bg-white overflow-hidden shadow-sm", className)}>
      <Table>
        <TableHeader>
          <TableRow className="bg-slate-50/75 hover:bg-slate-50/75">
            {columns.map((col, idx) => (
              <TableHead key={idx} className={cn("text-xs font-semibold text-slate-600", col.headerClassName)}>
                {col.header}
              </TableHead>
            ))}
          </TableRow>
        </TableHeader>
        <TableBody>
          {data.map((row, rowIdx) => {
            const key = keyExtractor(row, rowIdx);
            const clickable = Boolean(onRowClick);

            return (
              <TableRow
                key={key}
                onClick={() => onRowClick?.(row)}
                className={cn(
                  "transition-colors",
                  clickable && "cursor-pointer hover:bg-slate-50"
                )}
              >
                {columns.map((col, colIdx) => {
                  let content: React.ReactNode = null;
                  if (col.cell) {
                    content = col.cell(row);
                  } else if (col.accessorKey) {
                    content = String(row[col.accessorKey] ?? "");
                  }

                  return (
                    <TableCell key={colIdx} className={cn("py-3 text-sm text-slate-700", col.className)}>
                      {content}
                    </TableCell>
                  );
                })}
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </div>
  );
}
