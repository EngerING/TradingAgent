export function money(value: number | null | undefined) { return value == null ? 'No evaluable' : new Intl.NumberFormat('es-DO', { style: 'currency', currency: 'USD', minimumFractionDigits: 2, maximumFractionDigits: 4 }).format(value) }
export function number(value: number | null | undefined, digits = 2) { return value == null ? 'No evaluable' : new Intl.NumberFormat('es-DO', { maximumFractionDigits: digits }).format(value) }
export function percent(value: number | null | undefined) { return value == null ? 'No evaluable' : `${number(value * 100)}%` }
export function date(value: string | null | undefined) { return value ? new Date(value).toLocaleString('es-DO', { timeZone: 'America/Santo_Domingo', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit' }) : 'Sin observación' }
export function metric(value: number | null, format: string) { return format === 'money' ? money(value) : format === 'percent' ? percent(value) : number(value) }
