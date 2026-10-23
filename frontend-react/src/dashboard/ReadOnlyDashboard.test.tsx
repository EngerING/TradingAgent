import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router';
import { describe, expect, it, vi } from 'vitest';
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
});
