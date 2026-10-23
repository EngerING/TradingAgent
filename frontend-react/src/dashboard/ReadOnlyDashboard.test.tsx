import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { App } from '../App';
import { unavailableAdapter } from '../auth/contracts';
import type { AuthAdapter, AuthResult } from '../auth/contracts';

function preview(result: AuthResult = { kind: 'preview-complete' }): AuthAdapter {
  return { ...unavailableAdapter, mode: 'bff', source: 'preview',
    session: vi.fn().mockResolvedValue(result),
    activity: vi.fn().mockResolvedValue({ kind: 'preview-complete' }),
    logout: vi.fn().mockResolvedValue(undefined) };
}
function mount(adapter: AuthAdapter) {
  render(<MemoryRouter initialEntries={['/preview']}><App adapter={adapter} /></MemoryRouter>);
}
afterEach(() => { vi.useRealTimers(); vi.restoreAllMocks(); });

describe('Read-only dashboard', () => {
  it('renders verified empty financial states, segregated streams and no execution controls', async () => {
    mount(preview());
    expect(await screen.findByRole('heading', { name: 'A clearer view of every decision.' })).toBeVisible();
    expect(screen.getByText('OFFLINE / NO_TRADE')).toBeVisible();
    expect(screen.getByText('NO_TRADE')).toBeVisible();
    expect(screen.getByLabelText('Account capital: no verified data')).toBeVisible();
    expect(screen.getByLabelText('Net P&L: no verified data')).toBeVisible();
    expect(screen.getByRole('img', { name: /Decorative market illustration/ })).toBeVisible();
    expect(screen.getByText('Paper')).toBeVisible();
    expect(screen.getByText('Shadow')).toBeVisible();
    expect(screen.getByText('Forecast')).toBeVisible();
    expect(screen.getByRole('button', { name: /Market Analyst/ })).toBeDisabled();
    expect(screen.queryByRole('button', { name: /place order|buy|sell|live trading/i })).not.toBeInTheDocument();
  });

  it('shows security limits in a real navigation panel without changing permissions', async () => {
    const user = userEvent.setup(); mount(preview());
    await screen.findByRole('heading', { name: 'A clearer view of every decision.' });
    await user.click(screen.getByRole('button', { name: 'Session & security' }));
    expect(screen.getByRole('heading', { name: 'Session & access' })).toBeVisible();
    expect(screen.getByText('8 hours')).toBeVisible();
    expect(screen.getByText('30 minutes')).toBeVisible();
    expect(screen.getByText('PASSWORD_ONLY_DEV_PREVIEW')).toBeVisible();
    await user.click(screen.getByRole('button', { name: 'Overview' }));
    expect(screen.getByRole('heading', { name: 'A clearer view of every decision.' })).toBeVisible();
  });

  it('fails closed when the BFF rejects or expires the preview session', async () => {
    mount(preview({ kind: 'expired' }));
    expect(await screen.findByRole('heading', { name: 'Your session has expired' })).toBeVisible();
    expect(screen.queryByRole('heading', { name: 'A clearer view of every decision.' })).not.toBeInTheDocument();
  });

  it('waits for confirmation and never renders dashboard content optimistically', () => {
    const adapter = preview();
    adapter.session = vi.fn().mockReturnValue(new Promise<AuthResult>(() => {}));
    mount(adapter);
    expect(screen.getByRole('status')).toHaveTextContent('Checking your development session');
    expect(screen.queryByText('Account capital')).not.toBeInTheDocument();
    fireEvent(window, new Event('focus'));
    expect(adapter.session).toHaveBeenCalledTimes(1);
  });

  it('signs out through the existing BFF flow and returns to login', async () => {
    const user = userEvent.setup(); const adapter = preview(); mount(adapter);
    await screen.findByRole('heading', { name: 'A clearer view of every decision.' });
    await user.click(screen.getByRole('button', { name: 'Sign out' }));
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Welcome back' })).toBeVisible());
    expect(adapter.logout).toHaveBeenCalledTimes(1);
  });

  it('shows the 30-minute inactivity expiry even when a background check cannot finish', async () => {
    vi.useFakeTimers();
    const now = Date.now();
    const adapter = preview({ kind: 'preview-complete', expiresAt: new Date(now + 8 * 3600000).toISOString(),
      idleExpiresAt: new Date(now + 30 * 60000).toISOString() });
    mount(adapter);
    await act(async () => { await Promise.resolve(); });
    expect(screen.getByRole('heading', { name: 'A clearer view of every decision.' })).toBeVisible();
    await act(async () => { await vi.advanceTimersByTimeAsync(30 * 60000); });
    expect(screen.getByRole('heading', { name: 'Your session expired due to inactivity' })).toBeVisible();
    expect(screen.queryByText('Account capital')).not.toBeInTheDocument();
    expect(adapter.activity).not.toHaveBeenCalled(); // Passive GET never extends the deadline.
  });

  it('expires on focus after a sleeping tab missed its deadline timer', async () => {
    vi.useFakeTimers();
    const now = Date.now();
    const adapter = preview({ kind: 'preview-complete', expiresAt: new Date(now + 8 * 3600000).toISOString(),
      idleExpiresAt: new Date(now + 30 * 60000).toISOString() });
    mount(adapter);
    await act(async () => { await Promise.resolve(); });
    vi.setSystemTime(now + 31 * 60000); // Simulate sleep: advance the wall clock, not scheduled timers.
    await act(async () => { fireEvent(window, new Event('focus')); await Promise.resolve(); });
    expect(screen.getByRole('heading', { name: 'Your session expired due to inactivity' })).toBeVisible();
    expect(adapter.session).toHaveBeenCalledTimes(1); // No renewal or session recheck is needed to deny display.
  });

  it('only extends the idle deadline after the BFF confirms deliberate human activity', async () => {
    vi.useFakeTimers();
    vi.spyOn(document, 'hasFocus').mockReturnValue(true);
    const now = Date.now();
    let current: AuthResult = { kind: 'preview-complete', expiresAt: new Date(now + 8 * 3600000).toISOString(),
      idleExpiresAt: new Date(now + 30 * 60000).toISOString() };
    const adapter = preview(current);
    adapter.session = vi.fn().mockImplementation(async () => current);
    adapter.activity = vi.fn().mockImplementation(async () => {
      current = { kind: 'preview-complete', expiresAt: new Date(now + 8 * 3600000).toISOString(),
        idleExpiresAt: new Date(now + 40 * 60000).toISOString() };
      return current;
    });
    mount(adapter);
    await act(async () => { await Promise.resolve(); });
    await act(async () => { await vi.advanceTimersByTimeAsync(10 * 60000); });
    await act(async () => { fireEvent.pointerDown(document); await Promise.resolve(); });
    expect(adapter.activity).toHaveBeenCalledTimes(1);
    await act(async () => { await vi.advanceTimersByTimeAsync(21 * 60000); });
    expect(screen.getByRole('heading', { name: 'A clearer view of every decision.' })).toBeVisible();
    await act(async () => { await vi.advanceTimersByTimeAsync(9 * 60000); });
    expect(screen.getByRole('heading', { name: 'Your session expired due to inactivity' })).toBeVisible();
  });

  it('does not disguise a BFF outage before the known idle deadline as an ordinary expiry', async () => {
    const now = Date.now();
    const adapter = preview({ kind: 'preview-complete', expiresAt: new Date(now + 8 * 3600000).toISOString(),
      idleExpiresAt: new Date(now + 30 * 60000).toISOString() });
    adapter.session = vi.fn().mockResolvedValueOnce({ kind: 'preview-complete', expiresAt: new Date(now + 8 * 3600000).toISOString(),
      idleExpiresAt: new Date(now + 30 * 60000).toISOString() }).mockResolvedValueOnce({ kind: 'unavailable' });
    mount(adapter);
    await screen.findByRole('heading', { name: 'A clearer view of every decision.' });
    fireEvent(window, new Event('focus'));
    expect(await screen.findByRole('heading', { name: 'We’ll be right back' })).toBeVisible();
    expect(screen.queryByText('Account capital')).not.toBeInTheDocument();
  });

  it('shows the generic expiry at the absolute eight-hour boundary', async () => {
    vi.useFakeTimers();
    const now = Date.now();
    const deadline = new Date(now + 8 * 3600000).toISOString();
    const adapter = preview({ kind: 'preview-complete', expiresAt: deadline, idleExpiresAt: deadline });
    mount(adapter);
    await act(async () => { await Promise.resolve(); });
    await act(async () => { await vi.advanceTimersByTimeAsync(8 * 3600000); });
    expect(screen.getByRole('heading', { name: 'Your session has expired' })).toBeVisible();
  });
});
