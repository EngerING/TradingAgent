import { z } from 'zod'
import type { DashboardSnapshot, SolRequest, SolResponse } from './types'
const scalar = z.union([z.string(), z.number().finite(), z.null()])
const solSchema = z.object({ requestId: z.string().uuid(), status: z.string(), provider: z.string(), model: z.string().nullable(), text: z.string().max(4000),
  metrics: z.array(z.object({ label: z.string(), value: z.number().finite().nullable(), format: z.string() })),
  table: z.object({ columns: z.array(z.string()), rows: z.array(z.array(scalar)) }),
  chart: z.object({ title: z.string(), unit: z.string(), series: z.array(z.object({ name: z.string(), points: z.array(z.object({ at: z.string(), value: z.number().finite() })) })) }),
  warnings: z.array(z.string()), operationDetails: z.unknown().nullable(), prediction: z.unknown(),
  command: z.object({ intent: z.string(), status: z.literal('BLOCKED'), requiresConfirmation: z.boolean(), authorized: z.literal(false), reason: z.string() }).nullable(),
  usage: z.object({ inputTokens: z.number().nullable(), outputTokens: z.number().nullable(), estimatedCostUsd: z.number().nullable(), reservedCostUsd: z.number() }),
}).strict()
export function parseSolResponse(value: unknown): SolResponse { return solSchema.parse(value) as SolResponse }
export class ApiError extends Error { constructor(public status: number) { super(status === 401 ? 'Sesión requerida' : 'DATA_UNAVAILABLE') } }
export async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`/api/ui/${path}`, { credentials: 'same-origin', ...options, headers: { 'Content-Type': 'application/json', ...options?.headers } })
  if (!response.ok) throw new ApiError(response.status)
  return await response.json() as T
}
export const api = {
  snapshot: () => request<DashboardSnapshot>('dashboard'),
  session: () => request<{ authenticated: boolean }>('session'),
  login: (token: string) => request<{ authenticated: boolean }>('session', { method: 'POST', body: JSON.stringify({ token }) }),
  logout: () => request('session', { method: 'DELETE' }),
  chat: async (input: SolRequest) => parseSolResponse(await request<unknown>('sol/chat', { method: 'POST', body: JSON.stringify(input) })),
}
