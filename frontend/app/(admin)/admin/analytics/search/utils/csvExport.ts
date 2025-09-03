// frontend/app/(admin)/admin/analytics/search/utils/csvExport.ts
/**
 * Export data to CSV file
 */
import { at } from '@/lib/ts/safe';

export function exportToCSV(data: Record<string, unknown>[], filename: string) {
  if (!data || data.length === 0) {
    // Silently ignore empty export requests in production builds
    return;
  }

  // Get headers from first object
  const firstRow = at(data, 0);
  if (!firstRow) return;
  const headers = Object.keys(firstRow);

  // Create CSV content
  const csvContent = [
    // Headers
    headers.join(','),
    // Data rows
    ...data.map((row) =>
      headers
        .map((header) => {
          const value = row[header];
          // Escape quotes and wrap in quotes if contains comma
          if (typeof value === 'string' && (value.includes(',') || value.includes('"'))) {
            return `"${value.replace(/"/g, '""')}"`;
          }
          return value;
        })
        .join(',')
    ),
  ].join('\n');

  // Create blob and download
  const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
  const link = document.createElement('a');
  const url = URL.createObjectURL(blob);

  link.setAttribute('href', url);
  link.setAttribute('download', `${filename}-${new Date().toISOString().split('T')[0]}.csv`);
  link.style.visibility = 'hidden';

  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
}
