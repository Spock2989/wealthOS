"""
WealthOS Email Alert Service
============================
Sends transactional email alerts using SMTP (Gmail app password).

Configured via environment variables:
  SMTP_HOST     default: smtp.gmail.com
  SMTP_PORT     default: 587
  SMTP_USER     Gmail address used to send alerts (e.g. noreply@wlthos.in or a Gmail)
  SMTP_PASS     Gmail app password (NOT the account password)
  ALERT_EMAIL   Who receives alerts — default: tiwarikshitij20@gmail.com

Setup (one-time):
  1. Go to myaccount.google.com → Security → 2-Step Verification → App passwords
  2. Create an app password for "Mail" + "Other device" → name it "WealthOS"
  3. Copy the 16-char password into .env as SMTP_PASS

Failure policy:
  Email is best-effort — a failed send NEVER raises an exception or blocks
  the main request. All errors are logged. The lead/user is always saved first.
"""

import os
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

logger = logging.getLogger(__name__)

SMTP_HOST   = os.getenv("SMTP_HOST",   "smtp.gmail.com")
SMTP_PORT   = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER   = os.getenv("SMTP_USER",   "")
SMTP_PASS   = os.getenv("SMTP_PASS",   "")
ALERT_EMAIL = os.getenv("ALERT_EMAIL", "tiwarikshitij20@gmail.com")


def _send(subject: str, html_body: str, to: str = ALERT_EMAIL) -> bool:
    """
    Send an HTML email via SMTP/TLS. Returns True on success, False on failure.
    Never raises — caller is protected from email errors.
    """
    if not SMTP_USER or not SMTP_PASS:
        logger.warning(
            "Email not configured — set SMTP_USER and SMTP_PASS in .env. "
            "Subject: %s", subject
        )
        return False

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = f"WealthOS Alerts <{SMTP_USER}>"
        msg["To"]      = to
        msg.attach(MIMEText(html_body, "html"))

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as server:
            server.ehlo()
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.sendmail(SMTP_USER, [to], msg.as_string())

        logger.info("Alert sent: %s → %s", subject, to)
        return True

    except Exception as e:
        logger.error("Email send failed — %s: %s", subject, e)
        return False


# ── Alert: New Demo Request ─────────────────────────────────────
def alert_new_demo_request(
    ref_id: str,
    name: str,
    firm: str,
    email: str,
    phone: str,
    role: str = "",
    aum: str = "",
    clients: str = "",
    slot: str = "",
    message: str = "",
    source: str = "",
) -> bool:
    """
    Alert tiwarikshitij20@gmail.com immediately when someone books a demo.
    """
    ts = datetime.utcnow().strftime("%d %b %Y, %H:%M UTC")
    role_map = {
        "ria": "RIA", "mfd": "MFD", "family_office": "Family Office",
        "boutique": "Boutique Wealth", "pms": "PMS Manager",
        "aif": "AIF Manager", "bank": "Bank Wealth", "other": "Other",
    }
    slot_map = {
        "morning": "9am–12pm IST", "afternoon": "12pm–4pm IST",
        "evening": "4pm–7pm IST", "flexible": "Flexible",
    }

    html = f"""
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"/></head>
<body style="margin:0;padding:0;background:#f5f5f5;font-family:Inter,-apple-system,sans-serif">
<table width="100%" cellpadding="0" cellspacing="0" style="padding:32px 16px">
<tr><td align="center">
<table width="560" style="background:#fff;border:1px solid #e5e5e5;border-radius:8px;overflow:hidden">
  <!-- Header -->
  <tr><td style="background:#0A0A0A;padding:20px 28px">
    <span style="color:#fff;font-size:16px;font-weight:600">WealthOS</span>
    <span style="color:#5B7CFF;font-size:16px;font-weight:400"> Advisor OS</span>
    <span style="float:right;background:#1E40FF;color:#fff;font-size:11px;font-weight:600;padding:4px 10px;border-radius:4px;font-family:monospace">NEW DEMO REQUEST</span>
  </td></tr>
  <!-- Body -->
  <tr><td style="padding:28px">
    <h2 style="margin:0 0 4px;font-size:20px;color:#0A0A0A">{name}</h2>
    <p style="margin:0 0 24px;color:#737373;font-size:13px">{firm} · {role_map.get(role, role or '—')}</p>
    <table width="100%" style="border-collapse:collapse">
      {"".join([
        f'<tr><td style="padding:10px 0;border-bottom:1px solid #f0f0f0;color:#737373;font-size:12px;font-family:monospace;width:140px">{label}</td>'
        f'<td style="padding:10px 0;border-bottom:1px solid #f0f0f0;color:#0A0A0A;font-size:13px">{value}</td></tr>'
        for label, value in [
            ("REF ID",       ref_id),
            ("EMAIL",        f'<a href="mailto:{email}" style="color:#1E40FF">{email}</a>'),
            ("PHONE",        phone),
            ("AUM MANAGED",  aum or "—"),
            ("CLIENTS",      clients or "—"),
            ("PREFERRED SLOT", slot_map.get(slot, slot or "Flexible")),
            ("SOURCE",       source or "—"),
            ("SUBMITTED AT", ts),
        ]
      ])}
    </table>
    {f'<div style="margin-top:20px;padding:14px;background:#f9f9f9;border-radius:6px;font-size:13px;color:#525252;line-height:1.6"><b style="color:#0A0A0A">Message:</b><br>{message}</div>' if message else ''}
    <div style="margin-top:24px">
      <a href="mailto:{email}?subject=WealthOS+Demo+%5B{ref_id}%5D&body=Hi+{name.split()[0]},"
         style="display:inline-block;background:#0A0A0A;color:#fff;text-decoration:none;padding:10px 20px;border-radius:6px;font-size:13px;font-weight:500">
        Reply to {name.split()[0]} →
      </a>
    </div>
  </td></tr>
  <!-- Footer -->
  <tr><td style="background:#f9f9f9;padding:14px 28px;border-top:1px solid #e5e5e5">
    <span style="font-size:11px;color:#a3a3a3;font-family:monospace">wlthos.in · {ts} · Lead ID: {ref_id}</span>
  </td></tr>
</table>
</td></tr>
</table>
</body></html>
"""

    return _send(
        subject=f"[WealthOS] 🎯 New Demo Request — {name} ({firm})",
        html_body=html,
    )


# ── Alert: New Account Signup ───────────────────────────────────
def alert_new_signup(
    user_id: str,
    email: str,
    full_name: str,
    firm_name: str = "",
) -> bool:
    """
    Alert tiwarikshitij20@gmail.com when a new advisor creates an account.
    """
    ts = datetime.utcnow().strftime("%d %b %Y, %H:%M UTC")

    html = f"""
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"/></head>
<body style="margin:0;padding:0;background:#f5f5f5;font-family:Inter,-apple-system,sans-serif">
<table width="100%" cellpadding="0" cellspacing="0" style="padding:32px 16px">
<tr><td align="center">
<table width="560" style="background:#fff;border:1px solid #e5e5e5;border-radius:8px;overflow:hidden">
  <!-- Header -->
  <tr><td style="background:#0A0A0A;padding:20px 28px">
    <span style="color:#fff;font-size:16px;font-weight:600">WealthOS</span>
    <span style="color:#5B7CFF;font-size:16px;font-weight:400"> Advisor OS</span>
    <span style="float:right;background:#16A34A;color:#fff;font-size:11px;font-weight:600;padding:4px 10px;border-radius:4px;font-family:monospace">NEW ACCOUNT</span>
  </td></tr>
  <!-- Body -->
  <tr><td style="padding:28px">
    <h2 style="margin:0 0 4px;font-size:20px;color:#0A0A0A">{full_name}</h2>
    <p style="margin:0 0 24px;color:#737373;font-size:13px">{firm_name or 'Firm not specified'}</p>
    <table width="100%" style="border-collapse:collapse">
      {"".join([
        f'<tr><td style="padding:10px 0;border-bottom:1px solid #f0f0f0;color:#737373;font-size:12px;font-family:monospace;width:140px">{label}</td>'
        f'<td style="padding:10px 0;border-bottom:1px solid #f0f0f0;color:#0A0A0A;font-size:13px">{value}</td></tr>'
        for label, value in [
            ("USER ID",      user_id[:8] + "…"),
            ("EMAIL",        f'<a href="mailto:{email}" style="color:#1E40FF">{email}</a>'),
            ("FIRM",         firm_name or "—"),
            ("SIGNED UP AT", ts),
        ]
      ])}
    </table>
    <div style="margin-top:24px">
      <a href="mailto:{email}?subject=Welcome+to+WealthOS"
         style="display:inline-block;background:#0A0A0A;color:#fff;text-decoration:none;padding:10px 20px;border-radius:6px;font-size:13px;font-weight:500">
        Welcome {full_name.split()[0]} →
      </a>
    </div>
  </td></tr>
  <!-- Footer -->
  <tr><td style="background:#f9f9f9;padding:14px 28px;border-top:1px solid #e5e5e5">
    <span style="font-size:11px;color:#a3a3a3;font-family:monospace">wlthos.in · {ts}</span>
  </td></tr>
</table>
</td></tr>
</table>
</body></html>
"""

    return _send(
        subject=f"[WealthOS] ✅ New Signup — {full_name} ({email})",
        html_body=html,
    )
