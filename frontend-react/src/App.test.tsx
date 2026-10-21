import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router';
import { describe, expect, it } from 'vitest';
import { App } from './App';
import { createDemoAdapter } from './auth/demo';

function setup(path = '/') {
  const user = userEvent.setup();
  render(<MemoryRouter initialEntries={[path]}><App adapter={createDemoAdapter(1)} /></MemoryRouter>);
  return user;
}
describe('authentication surface', () => {
  it('renders reference copy and truthfully disables unsupported capabilities', () => {
    setup(); expect(screen.getByRole('heading', { name: 'Welcome back' })).toBeVisible();
    expect(screen.getByRole('button', { name: /Live Trading/ })).toBeDisabled();
    expect(screen.getByRole('button', { name: /Continue with Google/ })).toBeDisabled();
    expect(screen.getByRole('checkbox', { name: /Remember me/ })).toBeDisabled();
    expect(screen.getByText(/OFFLINE \/ NO_TRADE/)).toBeVisible();
  });
  it('reports invalid input without reflecting passwords', async () => {
    const user = setup(); await user.click(screen.getByRole('button', { name: 'Sign in' }));
    expect(screen.getByText('Enter a valid email address.')).toBeVisible();
    expect(screen.getByLabelText('Email address')).toHaveAttribute('aria-invalid', 'true');
  });
  it('toggles password visibility with an accessible button', async () => {
    const user = setup(); const input = screen.getByLabelText('Password', { exact: true });
    expect(input).toHaveAttribute('type', 'password');
    await user.click(screen.getByRole('button', { name: 'Show password' }));
    expect(input).toHaveAttribute('type', 'text');
    await user.click(screen.getByRole('button', { name: 'Hide password' }));
    expect(input).toHaveAttribute('type', 'password');
  });
  it('shows loading and completes only the explicitly simulated MFA flow', async () => {
    const user = setup(); await user.type(screen.getByLabelText('Email address'), 'demo@tradingagent.test');
    await user.type(screen.getByLabelText('Password', { exact: true }), 'InventedPassword8');
    await user.click(screen.getByRole('button', { name: 'Sign in' }));
    expect(await screen.findByRole('heading', { name: 'Set up two-step verification' })).toBeVisible();
    await user.click(screen.getByRole('button', { name: 'Continue to verification' }));
    await user.type(await screen.findByLabelText('Verification code'), '123456');
    await user.click(screen.getByRole('button', { name: 'Verify code' }));
    expect(await screen.findByRole('heading', { name: 'Demonstration complete' })).toBeVisible();
    expect(screen.getByText(/No real session has been created/)).toBeVisible();
  });
  it('register explains invitation-only access', async () => {
    const user = setup(); await user.click(screen.getByRole('button', { name: 'Register' }));
    expect(screen.getByRole('status')).toHaveTextContent('Access is by invitation only.');
  });
  it('navigates to recovery and keeps it explicitly simulated', async () => {
    const user = setup(); await user.click(screen.getByRole('link', { name: 'Forgot your password?' }));
    await user.type(screen.getByLabelText('Email address'), 'demo@tradingagent.test');
    await user.click(screen.getByRole('button', { name: 'Send recovery link' }));
    expect(await screen.findByRole('link', { name: 'Continue recovery demo' })).toBeVisible();
    expect(screen.getByText(/No email was sent/)).toBeVisible();
  });
  it('clears password and disables the submit control while waiting', async () => {
    const user = userEvent.setup();
    render(<MemoryRouter><App adapter={createDemoAdapter(100)} /></MemoryRouter>);
    await user.type(screen.getByLabelText('Email address'), 'demo@tradingagent.test');
    await user.type(screen.getByLabelText('Password', { exact:true }), 'InventedPassword8');
    await user.click(screen.getByRole('button', { name:'Sign in' }));
    expect(screen.getByRole('button', { name:/Please wait/ })).toBeDisabled();
    expect(screen.getByLabelText('Password', { exact:true })).toHaveValue('');
    expect(await screen.findByRole('heading', { name:'Set up two-step verification' })).toBeVisible();
  });
});
