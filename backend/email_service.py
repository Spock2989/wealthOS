"""
WealthOS — Email Service
Uses Resend API (resend.com) — free tier, 3k emails/month
Falls back to console log if RESEND_API_KEY not set (dev mode)

Setup:
  1. Sign up at resend.com (free)
  2. Add domain wlthos.in → copy DNS records to Cloudflare
  3. Get API key → add to .env: RESEND_API_KEY=re_xxxx
  4. Set FROM_EMAIL=noreply@wlthos.in in .env
"""

import os
import httpx
import logging
from pathlib import Path

log = logging.getLogger("email_service")

RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")
FROM_EMAIL = os.getenv("FROM_EMAIL", "WealthOS <noreply@wlthos.in>")
APP_URL = os.getenv("APP_URL", "https://wlthos.in")
API_URL = os.getenv("API_URL", "https://api.wlthos.in")


async def send_email(to: str, subject: str, html: str) -> bool:
    """Send email via Resend. Returns True on success."""
    if not RESEND_API_KEY:
        # Dev fallback — print to console
        log.warning(f"[EMAIL DEV MODE] To: {to} | Subject: {subject}")
        log.warning(f"[EMAIL DEV MODE] No RESEND_API_KEY set — email not sent")
        return True  # Don't block flow in dev

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(
                "https://api.resend.com/emails",
                headers={
                    "Authorization": f"Bearer {RESEND_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "from": FROM_EMAIL,
                    "to": [to],
                    "subject": subject,
                    "html": html,
                },
            )
            if r.status_code in (200, 201):
                log.info(f"Email sent to {to}: {subject}")
                return True
            else:
                log.error(f"Resend error {r.status_code}: {r.text}")
                return False
    except Exception as e:
        log.error(f"Email send failed: {e}")
        return False


# ── Email Templates ───────────────────────────────────────────────────────────

def verification_email(name: str, email: str, token: str) -> tuple[str, str]:
    verify_url = f"{API_URL}/v1/auth/verify?token={token}"
    subject = "Verify your WealthOS account"
    html = f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<style>
  body{{margin:0;padding:0;background:#0a0c10;font-family:'Inter',system-ui,sans-serif}}
  .wrap{{max-width:520px;margin:40px auto;background:#111318;border:1px solid #232839;border-radius:12px;overflow:hidden}}
  .header{{padding:28px 32px;border-bottom:1px solid #232839}}
  .logo{{display:flex;align-items:center;gap:10px}}
  .logo-icon{{width:28px;height:28px}}
  .logo-text{{font-size:17px;font-weight:700;color:#e8ecf4;letter-spacing:-.3px}}
  .body{{padding:32px}}
  .greeting{{font-size:22px;font-weight:700;color:#e8ecf4;margin-bottom:12px}}
  .text{{font-size:14px;color:#9ba3bc;line-height:1.6;margin-bottom:20px}}
  .btn{{display:inline-block;padding:13px 28px;background:#1E40FF;color:#fff;border-radius:8px;font-size:14px;font-weight:600;text-decoration:none;letter-spacing:-.1px}}
  .btn:hover{{background:#3358ff}}
  .divider{{height:1px;background:#232839;margin:24px 0}}
  .url-fallback{{font-size:11px;color:#5c6480;word-break:break-all;background:#0a0c10;padding:10px 12px;border-radius:6px;border:1px solid #232839}}
  .footer{{padding:20px 32px;font-size:11px;color:#5c6480;border-top:1px solid #232839}}
</style>
</head>
<body>
<div class="wrap">
  <div class="header">
    <div class="logo">
      <svg class="logo-icon" viewBox="0 0 28 28" fill="none">
        <rect x="2" y="6" width="16" height="16" rx="3" stroke="#e8ecf4" stroke-width="1.8"/>
        <rect x="10" y="6" width="16" height="16" rx="3" fill="#1E40FF" fill-opacity=".9"/>
      </svg>
      <span class="logo-text">WealthOS</span>
    </div>
  </div>
  <div class="body">
    <div class="greeting">Verify your account</div>
    <p class="text">Hi {name},<br><br>
    You're one step away from accessing WealthOS — institutional portfolio intelligence for Indian wealth advisors.<br><br>
    Click below to verify your email and activate your account.</p>
    <a href="{verify_url}" class="btn">Verify Email →</a>
    <div class="divider"></div>
    <p class="text" style="margin-bottom:8px;font-size:13px">If the button doesn't work, copy this link:</p>
    <div class="url-fallback">{verify_url}</div>
    <div class="divider"></div>
    <p class="text" style="font-size:12px;margin-bottom:0">This link expires in <strong style="color:#e8ecf4">24 hours</strong>. If you didn't create this account, ignore this email.</p>
  </div>
  <div class="footer">WealthOS AI · wlthos.in · Institutional Portfolio Intelligence</div>
</div>
</body>
</html>
"""
    return subject, html


def welcome_email(name: str, email: str) -> tuple[str, str]:
    login_url = f"{APP_URL}/app.html"
    subject = "Welcome to WealthOS — Your account is active"
    html = f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8"/>
<style>
  body{{margin:0;padding:0;background:#0a0c10;font-family:'Inter',system-ui,sans-serif}}
  .wrap{{max-width:520px;margin:40px auto;background:#111318;border:1px solid #232839;border-radius:12px;overflow:hidden}}
  .header{{padding:28px 32px;border-bottom:1px solid #232839;background:linear-gradient(135deg,#111318 0%,#1a2040 100%)}}
  .logo{{display:flex;align-items:center;gap:10px;margin-bottom:16px}}
  .logo-text{{font-size:17px;font-weight:700;color:#e8ecf4}}
  .badge{{font-size:10px;font-family:monospace;color:#1E40FF;background:#1E40FF22;padding:3px 8px;border-radius:4px;border:1px solid #1E40FF44}}
  .body{{padding:32px}}
  .greeting{{font-size:22px;font-weight:700;color:#e8ecf4;margin-bottom:12px}}
  .text{{font-size:14px;color:#9ba3bc;line-height:1.6;margin-bottom:20px}}
  .feature{{display:flex;gap:12px;margin-bottom:14px;padding:12px;background:#0a0c10;border-radius:8px;border:1px solid #232839}}
  .feature-icon{{font-size:20px;flex-shrink:0}}
  .feature-title{{font-size:13px;font-weight:600;color:#e8ecf4;margin-bottom:3px}}
  .feature-sub{{font-size:12px;color:#5c6480}}
  .btn{{display:inline-block;padding:13px 28px;background:#1E40FF;color:#fff;border-radius:8px;font-size:14px;font-weight:600;text-decoration:none}}
  .footer{{padding:20px 32px;font-size:11px;color:#5c6480;border-top:1px solid #232839}}
</style>
</head>
<body>
<div class="wrap">
  <div class="header">
    <div class="logo">
      <svg width="24" height="24" viewBox="0 0 28 28" fill="none">
        <rect x="2" y="6" width="16" height="16" rx="3" stroke="#e8ecf4" stroke-width="1.8"/>
        <rect x="10" y="6" width="16" height="16" rx="3" fill="#1E40FF"/>
      </svg>
      <span class="logo-text">WealthOS</span>
    </div>
    <span class="badge">ACCOUNT ACTIVE</span>
  </div>
  <div class="body">
    <div class="greeting">Welcome, {name} 👋</div>
    <p class="text">Your WealthOS account is verified and ready. Here's what you can do right now:</p>
    <div class="feature"><div class="feature-icon">📄</div><div><div class="feature-title">Upload CAS Statements</div><div class="feature-sub">CAMS · KFin · MF Central · Broker PDFs</div></div></div>
    <div class="feature"><div class="feature-icon">🔍</div><div><div class="feature-title">Portfolio Intelligence</div><div class="feature-sub">Look-through decomposition, overlap detection, factor DNA</div></div></div>
    <div class="feature"><div class="feature-icon">⚡</div><div><div class="feature-title">Scenario Simulation</div><div class="feature-sub">7 macro stress tests — US recession, RBI rate hike, oil shock</div></div></div>
    <div class="feature"><div class="feature-icon">✦</div><div><div class="feature-title">AI Review Memos</div><div class="feature-sub">Advisor-ready client commentary generated in seconds</div></div></div>
    <br>
    <a href="{login_url}" class="btn">Open Dashboard →</a>
  </div>
  <div class="footer">WealthOS AI · wlthos.in · Questions? Reply to this email.</div>
</div>
</body>
</html>
"""
    return subject, html


def password_reset_email(name: str, token: str) -> tuple[str, str]:
    reset_url = f"{APP_URL}/app.html?reset={token}"
    subject = "Reset your WealthOS password"
    html = f"""
<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"/>
<style>
  body{{margin:0;padding:0;background:#0a0c10;font-family:'Inter',system-ui,sans-serif}}
  .wrap{{max-width:520px;margin:40px auto;background:#111318;border:1px solid #232839;border-radius:12px;overflow:hidden}}
  .header{{padding:28px 32px;border-bottom:1px solid #232839}}
  .logo-text{{font-size:17px;font-weight:700;color:#e8ecf4}}
  .body{{padding:32px}}
  .title{{font-size:20px;font-weight:700;color:#e8ecf4;margin-bottom:10px}}
  .text{{font-size:14px;color:#9ba3bc;line-height:1.6;margin-bottom:20px}}
  .btn{{display:inline-block;padding:13px 28px;background:#1E40FF;color:#fff;border-radius:8px;font-size:14px;font-weight:600;text-decoration:none}}
  .warn{{font-size:12px;color:#B45309;background:#B4530922;padding:10px 14px;border-radius:6px;border:1px solid #B4530944;margin-top:20px}}
  .footer{{padding:20px 32px;font-size:11px;color:#5c6480;border-top:1px solid #232839}}
</style>
</head>
<body>
<div class="wrap">
  <div class="header"><span class="logo-text">WealthOS</span></div>
  <div class="body">
    <div class="title">Reset your password</div>
    <p class="text">Hi {name},<br><br>We received a request to reset your password. Click below to set a new one.</p>
    <a href="{reset_url}" class="btn">Reset Password →</a>
    <div class="warn">⚠ This link expires in 1 hour. If you didn't request a reset, your account is safe — ignore this email.</div>
  </div>
  <div class="footer">WealthOS AI · wlthos.in</div>
</div>
</body>
</html>
"""
    return subject, html
