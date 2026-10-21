export type IconName = 'mail' | 'lock' | 'eye' | 'eye-off' | 'arrow' | 'chart' | 'shield' | 'bolt' | 'info' | 'back' | 'check';
const paths: Record<IconName, string> = {
  mail: 'M3 5h18v14H3z M3 6l9 7 9-7', lock: 'M5 10h14v11H5z M8 10V6a4 4 0 018 0v4 M12 14v3',
  eye: 'M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12z M15 12a3 3 0 11-6 0 3 3 0 016 0',
  'eye-off': 'M3 3l18 18 M9 5.5A13 13 0 0112 5c6 0 10 7 10 7a19 19 0 01-4 4 M6 6c-3 2-4 6-4 6s4 7 10 7a13 13 0 005-1 M10 10a3 3 0 004 4',
  arrow: 'M3 12h18 M15 6l6 6-6 6', back: 'M21 12H3 M9 6l-6 6 6 6',
  chart: 'M3 21h19 M5 19v-6h3v6 M11 19V8h3v11 M17 19V2h3v17',
  shield: 'M12 2l9 4v6c0 6-9 10-9 10S3 18 3 12V6z M8 12l3 3 5-6',
  bolt: 'M14 2L4 14h7l-1 8 10-12h-7z', info: 'M12 11v6 M12 7v.1 M22 12a10 10 0 11-20 0 10 10 0 0120 0',
  check: 'M4 12l5 5L20 6',
};
export function Icon({ name }: { name: IconName }) {
  if (name === 'shield') return <svg viewBox="0 0 24 24" className="icon" aria-hidden="true"><path fill="currentColor" d="M12 2l9 4v6c0 6-9 10-9 10S3 18 3 12V6z"/><path fill="none" stroke="white" strokeWidth="1.5" d="M8 12l3 3 5-6"/></svg>;
  return <svg viewBox="0 0 24 24" aria-hidden="true" className="icon" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"><path d={paths[name]} /></svg>;
}
export function Mark() {
  return <svg className="brand-mark" viewBox="3 3 42 42" aria-hidden="true">
    {Array.from({ length: 10 }, (_, i) => <path key={i} transform={`rotate(${i * 36} 24 24)`} fill={i % 2 ? '#2666a0' : '#4b87bb'} stroke="#ffffff" strokeWidth=".45" d="M24 24C19 19 17 11 20 5C22 1 27 2 29 6C32 13 27 20 24 24Z" />)}
    <circle cx="24" cy="24" r="2.8" fill="#fff" />
  </svg>;
}
export function GoogleMark() {
  return <svg width="25" height="25" viewBox="0 0 24 24" aria-hidden="true"><path fill="#4285f4" d="M22 12.2c0-.7-.1-1.4-.2-2.2H12v4.2h5.6a4.8 4.8 0 01-2.1 3.2V20h3.4c2-1.8 3.1-4.4 3.1-7.8"/><path fill="#34a853" d="M12 22c2.8 0 5.2-.9 6.9-2.5l-3.4-2.6c-.9.6-2.1 1-3.5 1-2.7 0-5-1.8-5.8-4.2H2.7v2.7A10.4 10.4 0 0012 22"/><path fill="#fbbc05" d="M6.2 13.7a6 6 0 010-3.4V7.6H2.7a10 10 0 000 8.8z"/><path fill="#ea4335" d="M12 6.1c1.5 0 2.8.5 3.8 1.5L18.7 5A10 10 0 0012 2a10.4 10.4 0 00-9.3 5.6l3.5 2.7C7 7.9 9.3 6.1 12 6.1"/></svg>;
}
