from __future__ import annotations

import json
import os
from typing import Any

from src.detector.anomaly import AnomalyResult, DetectionReport
from src.remediator.resources import RemediationReport


class SlackNotifier:
    def __init__(self, webhook_url: str | None = None):
        self.webhook_url = webhook_url or os.environ.get("SLACK_WEBHOOK_URL", "")

    def send(self, detection: DetectionReport, remediation: RemediationReport) -> bool:
        if not self.webhook_url:
            return False

        blocks = self._build_blocks(detection, remediation)
        payload = {
            "text": (
                f"CostGuard Report: {detection.burn_rate_direction.upper()}"
                f" — ${detection.projected_monthly_cost}/mo projected"
            ),
            "blocks": blocks,
        }
        return self._post(payload)

    def _build_blocks(
        self, detection: DetectionReport, remediation: RemediationReport
    ) -> list[dict[str, Any]]:
        blocks: list[dict[str, Any]] = [
            self._header_block(detection),
            {"type": "divider"},
            self._cost_summary_block(detection),
            {"type": "divider"},
        ]

        if detection.anomalies:
            blocks.append(self._anomalies_block(detection.anomalies))
            blocks.append({"type": "divider"})

        if remediation.resources:
            blocks.append(self._remediation_block(remediation))
            blocks.append({"type": "divider"})

        blocks.append(self._action_block())
        return blocks

    def _header_block(self, detection: DetectionReport) -> dict[str, Any]:
        emoji = {"increasing": "🔥", "decreasing": "✅", "stable": "✅"}
        return {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": (
                    f"{emoji.get(detection.burn_rate_direction, '📊')}"
                    f" CostGuard Report — {detection.burn_rate_direction.title()} Spend"
                ),
            },
        }

    def _cost_summary_block(self, detection: DetectionReport) -> dict[str, Any]:
        fields = [
            self._mrkdwn_field("*📅 7-Day Total*", f"${detection.total_cost_last_7_days:,.2f}"),
            self._mrkdwn_field("*📈 Avg Daily*", f"${detection.avg_daily_cost:,.2f}"),
            self._mrkdwn_field(
                "*📊 Projected Monthly*", f"${detection.projected_monthly_cost:,.2f}"
            ),

            self._mrkdwn_field(
                "*📉 Previous Month*", f"${detection.previous_monthly_cost:,.2f}"
            ),
            self._mrkdwn_field("*⚠️ Anomalies Found*", str(len(detection.anomalies))),
            self._mrkdwn_field("*📉 Std Dev*", f"${detection.std_dev:,.2f}"),
        ]

        diff = detection.projected_monthly_cost - detection.previous_monthly_cost
        diff_str = f"+${diff:,.2f} 🔴" if diff > 0 else f"${diff:,.2f} 🟢"
        fields.append(
            self._mrkdwn_field("*📈 MoM Change*", diff_str)
        )

        return {
            "type": "section",
            "fields": fields,
        }

    def _anomalies_block(self, anomalies: list[AnomalyResult]) -> dict[str, Any]:
        lines = ["*🔍 Top Cost Anomalies (z-score ≥ 2.0)*\n"]
        for a in anomalies[:5]:
            emoji = self._severity_emoji(a.severity)
            lines.append(
                f"{emoji} *{a.date}* — ${a.actual_cost:,.2f} vs ${a.expected_cost:,.2f} "
                f"(z={a.z_score:+.1f}, {a.deviation_percent:+.1f}%)"
            )
        return {
            "type": "section",
            "text": self._mrkdwn_text("\n".join(lines)),
        }

    def _remediation_block(self, remediation: RemediationReport) -> dict[str, Any]:
        lines = [f"*🧹 Orphaned Resources Found ({remediation.total_orphaned_count})*"]
        lines.append(
            f"*Estimated Monthly Waste:* ${remediation.total_estimated_savings:,.2f}"
        )
        status = "Enabled ✅" if remediation.auto_remediation_enabled else "Disabled ⚠️"
        lines.append(f"*Auto-Remediation:* {status}")
        lines.append("")
        for r in remediation.resources[:8]:
            emoji = self._resource_emoji(r.resource_type)
            cost_str = f"${r.estimated_monthly_cost:.2f}/mo"
            lines.append(
                f"{emoji} `{r.resource_type}` `{r.resource_id}` — {cost_str} — {r.reason}"
            )
        if len(remediation.resources) > 8:
            lines.append(f"...and {len(remediation.resources) - 8} more")
        return {
            "type": "section",
            "text": self._mrkdwn_text("\n".join(lines)),
        }

    def _action_block(self) -> dict[str, Any]:
        return {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "📋 View Full Report"},
                    "url": os.environ.get("COSTGUARD_DASHBOARD_URL", ""),
                    "style": "primary",
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "🚀 Trigger Remediation"},
                    "url": os.environ.get("COSTGUARD_REMEDIATE_URL", ""),
                    "style": "danger",
                },
            ],
        }

    @staticmethod
    def _mrkdwn_field(title: str, value: str) -> dict[str, Any]:
        return {"type": "mrkdwn", "text": f"{title}\n{value}"}

    @staticmethod
    def _mrkdwn_text(text: str) -> dict[str, Any]:
        return {"type": "mrkdwn", "text": text}

    @staticmethod
    def _severity_emoji(severity: str) -> str:
        return {"critical": "🔥", "high": "🔴", "medium": "🟡", "low": "🟢"}.get(severity, "⚪")

    @staticmethod
    def _resource_emoji(resource_type: str) -> str:
        return {
            "ebs_volume": "💾",
            "eip": "🌐",
            "load_balancer": "⚖️",
            "snapshot": "📸",
        }.get(resource_type, "📦")

    def _post(self, payload: dict[str, Any]) -> bool:
        import urllib.request as req

        data = json.dumps(payload).encode()
        headers = {"Content-Type": "application/json"}
        try:
            r = req.Request(self.webhook_url, data=data, headers=headers, method="POST")
            resp = req.urlopen(r, timeout=10)
            return resp.status == 200
        except Exception:
            return False
