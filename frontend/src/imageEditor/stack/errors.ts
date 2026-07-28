/**
 * Turn an API failure into one sentence of fact.
 *
 * A raw FastAPI validation payload is a JSON array of pydantic objects. Dumping
 * that on screen states nothing the reader can act on, so it is reduced to the
 * fields that failed.
 */
export function apiErrorMessage(err: any, fallback: string): string {
  const detail = err?.response?.data?.detail

  if (typeof detail === 'string' && detail) return detail

  if (Array.isArray(detail)) {
    const fields = detail
      .map((item: any) => (Array.isArray(item?.loc) ? item.loc.filter((p: any) => p !== 'body').join('.') : null))
      .filter(Boolean)
    if (fields.length) {
      return `The request was rejected: ${[...new Set(fields)].join(', ')}.`
    }
  }

  if (typeof err?.message === 'string' && err.message) return err.message
  return fallback
}
