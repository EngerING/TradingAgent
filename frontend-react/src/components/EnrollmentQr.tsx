import qrcode from 'qrcode-generator';
// Re-encode the vetted URI locally. Provider SVG/HTML is never rendered.
export function EnrollmentQr({ uri }: { uri: string }) {
  const qr = qrcode(0, 'M'); qr.addData(uri); qr.make(); const count = qr.getModuleCount();
  const cells: string[] = [];
  for (let y = 0; y < count; y++) for (let x = 0; x < count; x++) if (qr.isDark(y, x)) cells.push(`M${x + 4},${y + 4}h1v1h-1z`);
  return <div className="qr-placeholder"><svg viewBox={`0 0 ${count + 8} ${count + 8}`} role="img" aria-label="Authenticator enrollment QR. Keep private."><rect width="100%" height="100%" fill="white"/><path d={cells.join('')} fill="black"/></svg></div>;
}
