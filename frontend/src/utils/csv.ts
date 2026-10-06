type CsvValue = string | number | boolean | null

/** Quote every cell and prevent spreadsheet applications interpreting user text as formulas. */
export function buildCsv(headers: string[], rows: CsvValue[][]): string {
  const escape = (value: CsvValue) => {
    let text = value === null ? '' : String(value)
    // Ignore leading control bytes when checking for spreadsheet formula prefixes.
    // eslint-disable-next-line no-control-regex
    if (typeof value === 'string' && /^[\s\u0000-\u001f]*[=+@-]/.test(text)) text = `'${text}`
    return `"${text.replace(/"/g, '""')}"`
  }
  return [headers, ...rows].map((row) => row.map(escape).join(',')).join('\r\n')
}

export function downloadClientCsv(filename: string, headers: string[], rows: CsvValue[][]) {
  const url = URL.createObjectURL(new Blob(['\uFEFF', buildCsv(headers, rows)], { type: 'text/csv;charset=utf-8' }))
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  URL.revokeObjectURL(url)
}
