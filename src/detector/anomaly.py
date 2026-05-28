import statistics

from pydantic import BaseModel

from src.collector.cost_explorer import DailyCost


class AnomalyResult(BaseModel):
    date: str
    actual_cost: float
    expected_cost: float
    z_score: float
    severity: str  # low, medium, high, critical
    deviation_percent: float


class DetectionReport(BaseModel):
    total_cost_last_7_days: float
    avg_daily_cost: float
    std_dev: float
    anomalies: list[AnomalyResult]
    projected_monthly_cost: float
    previous_monthly_cost: float
    burn_rate_direction: str  # increasing, stable, decreasing


class AnomalyDetector:
    def __init__(self, z_score_threshold: float = 2.0, min_data_points: int = 7):
        self.z_score_threshold = z_score_threshold
        self.min_data_points = min_data_points

    def analyze(self, daily_costs: list[DailyCost]) -> DetectionReport:
        if len(daily_costs) < self.min_data_points:
            return DetectionReport(
                total_cost_last_7_days=0,
                avg_daily_cost=0,
                std_dev=0,
                anomalies=[],
                projected_monthly_cost=0,
                previous_monthly_cost=0,
                burn_rate_direction="stable",
            )

        amounts = [c.amount for c in daily_costs]

        if len(amounts) >= 7:
            recent = amounts[-7:]
        else:
            recent = amounts

        mean = statistics.mean(recent)
        std = statistics.pstdev(recent) or 0.01

        anomalies: list[AnomalyResult] = []
        for c in daily_costs:
            z = (c.amount - mean) / std
            if abs(z) >= self.z_score_threshold:
                deviation = ((c.amount - mean) / mean) * 100
                anomalies.append(
                    AnomalyResult(
                        date=c.date,
                        actual_cost=c.amount,
                        expected_cost=round(mean, 2),
                        z_score=round(z, 2),
                        severity=self._classify_severity(z, deviation),
                        deviation_percent=round(deviation, 1),
                    )
                )

        total_last_7 = sum(c.amount for c in daily_costs[-7:])
        avg = round(statistics.mean(amounts[-7:]), 2)
        projected = round(avg * 30, 2)

        prev_7 = amounts[-14:-7] if len(amounts) >= 14 else amounts[:7]
        prev_avg = statistics.mean(prev_7) if prev_7 else avg
        prev_projected = round(prev_avg * 30, 2)

        direction = (
            "increasing" if projected > prev_projected * 1.1
            else "decreasing" if projected < prev_projected * 0.9
            else "stable"
        )

        return DetectionReport(
            total_cost_last_7_days=round(total_last_7, 2),
            avg_daily_cost=avg,
            std_dev=round(std, 2),
            anomalies=sorted(anomalies, key=lambda a: a.z_score, reverse=True),
            projected_monthly_cost=projected,
            previous_monthly_cost=prev_projected,
            burn_rate_direction=direction,
        )

    @staticmethod
    def _classify_severity(z_score: float, deviation_pct: float) -> str:
        if abs(z_score) > 5 or abs(deviation_pct) > 100:
            return "critical"
        if abs(z_score) > 3 or abs(deviation_pct) > 50:
            return "high"
        if abs(z_score) > 2 or abs(deviation_pct) > 25:
            return "medium"
        return "low"
