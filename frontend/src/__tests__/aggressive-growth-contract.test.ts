import { execFileSync } from 'node:child_process'
import { existsSync } from 'node:fs'
import { join, resolve } from 'node:path'
import { expect, it } from 'vitest'
import { aggressiveGrowthSchema } from '../modules/aggressive-growth/contracts'

it('accepts the real Python projection without coercing unknown evidence or granting Paper authority', () => {
  const root = resolve(process.cwd(), '..') // npm test runs from the frontend package.
  const python = join(root, '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python')
  expect(existsSync(python)).toBe(true)
  // Entirely synthetic test state. No database, broker, market feed or API request.
  const source = `
import json
from datetime import datetime
from trading_agent.aggressive_growth import configuration, initial_state
from trading_agent.aggressive_growth_projection import project
at = '2026-10-10T12:00:00+00:00'
state = initial_state(configuration('.'), 'a'*64, at)
state['portfolios']['R20']['financing_cost'] = None
payload = dict(experiment='aggressive-r20-'+'a'*32, scope='AGGRESSIVE_GROWTH_R20',
    classification='SHADOW_SIMULATED', broker_orders=0, live_enabled=False, state=state)
print(json.dumps(project(payload, datetime.fromisoformat(at))))
`
  const raw = execFileSync(python, ['-c', source], {
    cwd: root, encoding: 'utf8', timeout: 10000,
    env: { ...process.env, PYTHONPATH: join(root, 'python') },
  })
  const view = aggressiveGrowthSchema.parse(JSON.parse(raw))
  expect(view.equity).toBe('100')
  expect(view.financing).toBeNull()
  expect(view.winRate).toBeNull()
  expect(view.kronos.calibratedProbability).toBeNull()
  expect(view.paper.authorizationGranted).toBe(false)
  expect(view.classification).toBe('SHADOW_SIMULATED')
})
