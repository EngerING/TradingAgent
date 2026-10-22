import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router';
import { App } from '../App';
import { unavailableAdapter } from './contracts';
import type { AuthResult } from './contracts';
afterEach(() => vi.useRealTimers());
it('coalesces interval and focus checks while a valid session read is pending', async () => {
  let resolve!: (result: AuthResult) => void;
  const session = vi.fn().mockImplementation(() => new Promise<AuthResult>(done => { resolve = done; }));
  render(<MemoryRouter initialEntries={['/session/complete']}><App adapter={{ ...unavailableAdapter, mode: 'bff', session }} /></MemoryRouter>);
  expect(session).toHaveBeenCalledTimes(1); fireEvent(window, new Event('focus')); expect(session).toHaveBeenCalledTimes(1);
  await act(async () => { resolve({ kind: 'complete' }); }); expect(screen.getByRole('heading', { name: 'Identity authenticated' })).toBeVisible();
});
it('failed logout from an error screen remains explicitly unconfirmed without unhandled rejection', async () => {
  const logout = vi.fn().mockRejectedValue(new Error('LOGOUT_UNCONFIRMED'));
  render(<MemoryRouter initialEntries={['/session/expired']}><App adapter={{ ...unavailableAdapter, mode: 'bff', logout }} /></MemoryRouter>);
  fireEvent.click(screen.getByRole('button', { name: 'Return to sign in' }));
  await waitFor(() => expect(screen.getByText(/The result could not be confirmed/)).toBeVisible()); expect(logout).toHaveBeenCalledTimes(1);
});
