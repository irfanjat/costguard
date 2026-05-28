from __future__ import annotations

import json
import os
from datetime import UTC
from typing import Any

import boto3

from src.collector.cost_explorer import CostExplorerClient
from src.detector.anomaly import AnomalyDetector
from src.notifier.slack import SlackNotifier
from src.remediator.resources import ResourceScanner


class CostGuard:
    def __init__(self, event: dict[str, Any], context: Any = None):
        self.event = event
        self.context = context
        self.session = boto3.Session()
        self.dynamodb = self.session.resource("dynamodb")
        self.history_table = self._get_history_table()

    def run(self) -> dict[str, Any]:
        try:
            cost_data = self._collect_costs()
            detection = self._detect_anomalies(cost_data)
            remediation = self._scan_resources()
            self._notify(detection, remediation)
            self._store_history(detection, remediation)
            return self._response(200, "CostGuard run completed successfully")
        except Exception as e:
            return self._response(500, f"CostGuard run failed: {e}")

    def _collect_costs(self) -> list:
        days = int(os.environ.get("COSTGUARD_LOOKBACK_DAYS", "14"))
        client = CostExplorerClient(days_back=days, session=self.session)
        return client.get_daily_costs()

    def _detect_anomalies(self, cost_data: list):
        threshold = float(os.environ.get("COSTGUARD_ZSCORE_THRESHOLD", "2.0"))
        detector = AnomalyDetector(z_score_threshold=threshold)
        return detector.analyze(cost_data)

    def _scan_resources(self):
        regions_str = os.environ.get("COSTGUARD_REGIONS", "")
        regions = regions_str.split(",") if regions_str else None
        auto_remediate = os.environ.get("COSTGUARD_AUTO_REMEDIATE", "false").lower() == "true"
        scanner = ResourceScanner(
            session=self.session,
            regions=regions,
            auto_remediate=auto_remediate,
        )
        return scanner.scan()

    def _notify(self, detection, remediation):
        notifier = SlackNotifier()
        notifier.send(detection, remediation)

    def _get_history_table(self):
        table_name = os.environ.get("COSTGUARD_HISTORY_TABLE", "costguard-history")
        try:
            return self.dynamodb.Table(table_name)
        except Exception:
            return None

    def _store_history(self, detection, remediation):
        if not self.history_table:
            return
        item = {
            "run_id": self._run_id(),
            "timestamp": self._iso_now(),
            "detection": detection.model_dump(mode="json"),
            "remediation": remediation.model_dump(mode="json"),
        }
        try:
            self.history_table.put_item(Item=item)
        except Exception:
            pass

    @staticmethod
    def _run_id() -> str:
        import uuid
        return str(uuid.uuid4())

    @staticmethod
    def _iso_now() -> str:
        from datetime import datetime
        return datetime.now(UTC).isoformat()

    @staticmethod
    def _response(status: int, message: str) -> dict[str, Any]:
        return {"statusCode": status, "body": json.dumps({"message": message})}


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    guard = CostGuard(event, context)
    return guard.run()
