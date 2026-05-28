from src.collector.cost_explorer import DailyCost
from src.detector.anomaly import AnomalyDetector


def _make_costs(values: list[float]) -> list[DailyCost]:
    return [
        DailyCost(date=f"2026-{m:02d}-{d:02d}", amount=v, services={})
        for d, v in enumerate(values, start=1)
        for m in [5]
    ]


def test_no_anomalies_with_stable_data():
    costs = _make_costs([10.0] * 14)
    report = AnomalyDetector().analyze(costs)
    assert len(report.anomalies) == 0
    assert report.burn_rate_direction == "stable"


def test_detects_single_spike():
    vals = [10.0] * 13 + [50.0]
    costs = _make_costs(vals)
    report = AnomalyDetector(z_score_threshold=2.0).analyze(costs)
    assert len(report.anomalies) >= 1
    anomaly = report.anomalies[0]
    assert anomaly.actual_cost == 50.0
    assert anomaly.z_score > 2.0


def test_detects_drop():
    vals = [10.0] * 13 + [2.0]
    costs = _make_costs(vals)
    report = AnomalyDetector(z_score_threshold=2.0).analyze(costs)
    assert len(report.anomalies) >= 1
    assert report.anomalies[0].actual_cost == 2.0


def test_insufficient_data_returns_empty():
    costs = _make_costs([10.0, 10.0])
    report = AnomalyDetector(min_data_points=7).analyze(costs)
    assert len(report.anomalies) == 0
    assert report.avg_daily_cost == 0


def test_burn_rate_increasing():
    vals = [10.0] * 7 + [15.0] * 7
    costs = _make_costs(vals)
    report = AnomalyDetector().analyze(costs)
    assert report.burn_rate_direction == "increasing"


def test_burn_rate_decreasing():
    vals = [15.0] * 7 + [10.0] * 7
    costs = _make_costs(vals)
    report = AnomalyDetector().analyze(costs)
    assert report.burn_rate_direction == "decreasing"


def test_projected_monthly_cost():
    vals = [10.0] * 14
    costs = _make_costs(vals)
    report = AnomalyDetector().analyze(costs)
    assert report.avg_daily_cost == 10.0
    assert report.projected_monthly_cost == 300.0


def test_classify_severity():
    detector = AnomalyDetector()
    assert detector._classify_severity(6.0, 200) == "critical"
    assert detector._classify_severity(4.0, 60) == "high"
    assert detector._classify_severity(2.5, 30) == "medium"
    assert detector._classify_severity(1.0, 10) == "low"
