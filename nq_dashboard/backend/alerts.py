"""Email alerts via Resend API — signal entry, exit, and daily summary."""

import logging

import resend

from dashboard_config import RESEND_API_KEY, EMAIL_RECIPIENT

logger = logging.getLogger(__name__)


class EmailAlert:
    def __init__(self):
        self.enabled = bool(RESEND_API_KEY)
        if self.enabled:
            resend.api_key = RESEND_API_KEY
        self.recipient = EMAIL_RECIPIENT
        self.from_email = "NQ Scalper <onboarding@resend.dev>"

    async def send_signal(self, signal_data: dict):
        if not self.enabled:
            logger.info("Email alerts disabled (no API key)")
            return

        sl_price = signal_data.get("sl_price", 0)
        tp1_price = signal_data.get("tp1_price", 0)
        close = signal_data.get("close", 0)
        sl_distance = signal_data.get("sl_distance", 0)
        tp1_distance = signal_data.get("tp1_distance", 0)

        subject = f"NQ LONG SIGNAL - Score {signal_data.get('long_score', 0):.1f}"

        html = f"""
        <div style="font-family: 'Courier New', monospace; background: #0a0e17; color: #e5e7eb; padding: 20px; border-radius: 8px;">
            <h2 style="color: #10b981; margin-top: 0;">NQ LONG SIGNAL</h2>
            <hr style="border-color: #374151;">
            <table style="width: 100%; color: #e5e7eb;">
                <tr><td style="color: #9ca3af;">Score:</td><td><strong>{signal_data.get('long_score', 0):.1f}</strong> / {signal_data.get('long_threshold', 0):.1f}</td></tr>
                <tr><td style="color: #9ca3af;">Price:</td><td><strong>{close:,.1f}</strong></td></tr>
                <tr><td style="color: #9ca3af;">ATR%:</td><td>{signal_data.get('atr_percentile', 0):.0f}%</td></tr>
                <tr><td style="color: #9ca3af;">SL:</td><td style="color: #ef4444;">{sl_price:,.1f} (-{sl_distance:.0f}pts)</td></tr>
                <tr><td style="color: #9ca3af;">TP1:</td><td style="color: #10b981;">{tp1_price:,.1f} (+{tp1_distance:.0f}pts)</td></tr>
                <tr><td style="color: #9ca3af;">Session:</td><td>{signal_data.get('session', 'US')}</td></tr>
            </table>
            <hr style="border-color: #374151;">
            <p style="color: #6b7280; font-size: 12px;">Paper Trade - NQ Swing Scalper B1</p>
        </div>
        """

        await self._send(subject, html)

    async def send_exit(self, trade: dict):
        if not self.enabled:
            return

        pnl = trade.get("total_pnl", 0)
        is_win = pnl > 0
        pnl_color = "#10b981" if is_win else "#ef4444"
        result = "WIN" if is_win else "LOSS"
        subject = f"NQ TRADE {result} - ${pnl:,.0f} ({trade.get('exit_reason', '')})"

        html = f"""
        <div style="font-family: 'Courier New', monospace; background: #0a0e17; color: #e5e7eb; padding: 20px; border-radius: 8px;">
            <h2 style="color: {pnl_color}; margin-top: 0;">TRADE CLOSED</h2>
            <hr style="border-color: #374151;">
            <table style="width: 100%; color: #e5e7eb;">
                <tr><td style="color: #9ca3af;">Exit Reason:</td><td><strong>{trade.get('exit_reason', '')}</strong></td></tr>
                <tr><td style="color: #9ca3af;">P&L:</td><td style="color: {pnl_color};"><strong>${pnl:,.0f}</strong></td></tr>
                <tr><td style="color: #9ca3af;">Entry:</td><td>{trade.get('entry_price', 0):,.1f}</td></tr>
                <tr><td style="color: #9ca3af;">Exit:</td><td>{trade.get('exit_price', 0):,.1f}</td></tr>
                <tr><td style="color: #9ca3af;">TP1 Hit:</td><td>{'Yes' if trade.get('tp1_hit') else 'No'}</td></tr>
                <tr><td style="color: #9ca3af;">Trail Stage:</td><td>S{trade.get('trail_stage', 0)}</td></tr>
            </table>
            <hr style="border-color: #374151;">
            <p style="color: #6b7280; font-size: 12px;">Paper Trade - NQ Swing Scalper B1</p>
        </div>
        """

        await self._send(subject, html)

    async def send_daily_summary(self, stats: dict):
        if not self.enabled:
            return

        subject = f"NQ Daily Summary - ${stats.get('today_pnl', 0):,.0f} today"

        html = f"""
        <div style="font-family: 'Courier New', monospace; background: #0a0e17; color: #e5e7eb; padding: 20px; border-radius: 8px;">
            <h2 style="color: #3b82f6; margin-top: 0;">Daily Summary</h2>
            <hr style="border-color: #374151;">
            <table style="width: 100%; color: #e5e7eb;">
                <tr><td style="color: #9ca3af;">Today P&L:</td><td><strong>${stats.get('today_pnl', 0):,.0f}</strong></td></tr>
                <tr><td style="color: #9ca3af;">Today Trades:</td><td>{stats.get('today_trades', 0)}</td></tr>
                <tr><td style="color: #9ca3af;">Total P&L:</td><td>${stats.get('total_pnl', 0):,.0f}</td></tr>
                <tr><td style="color: #9ca3af;">Win Rate:</td><td>{stats.get('win_rate', 0):.1f}%</td></tr>
                <tr><td style="color: #9ca3af;">Profit Factor:</td><td>{stats.get('pf', 0):.2f}</td></tr>
                <tr><td style="color: #9ca3af;">Total Trades:</td><td>{stats.get('total_trades', 0)}</td></tr>
                <tr><td style="color: #9ca3af;">Current DD:</td><td>${stats.get('max_dd', 0):,.0f}</td></tr>
            </table>
            <p style="color: #6b7280; font-size: 12px;">Paper Trade - NQ Swing Scalper B1</p>
        </div>
        """

        await self._send(subject, html)

    async def _send(self, subject: str, html_body: str):
        try:
            params: resend.Emails.SendParams = {
                "from": self.from_email,
                "to": [self.recipient],
                "subject": subject,
                "html": html_body,
            }
            email = resend.Emails.send(params)
            logger.info("Email sent: %s (id: %s)", subject, email.get("id"))
        except Exception as e:
            logger.error("Email failed: %s", e)
