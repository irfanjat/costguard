from datetime import UTC, datetime, timedelta

import boto3
from pydantic import BaseModel


class DailyCost(BaseModel):
    date: str
    amount: float
    services: dict[str, float]


class CostExplorerClient:
    def __init__(self, days_back: int = 14, session: boto3.Session | None = None):
        self.days_back = days_back
        self.client = (session or boto3.Session()).client("ce")

    def get_daily_costs(self) -> list[DailyCost]:
        end = datetime.now(UTC)
        start = end - timedelta(days=self.days_back)

        response = self.client.get_cost_and_usage(
            TimePeriod={
                "Start": start.strftime("%Y-%m-%d"),
                "End": end.strftime("%Y-%m-%d"),
            },
            Granularity="DAILY",
            Metrics=["UnblendedCost"],
            GroupBy=[{"Type": "DIMENSION", "Key": "SERVICE"}],
        )

        results: list[DailyCost] = []
        for day in response.get("ResultsByTime", []):
            date = day["TimePeriod"]["Start"]
            total = float(day["Total"]["UnblendedCost"]["Amount"])
            services = {}
            for group in day.get("Groups", []):
                service_name = group["Keys"][0]
                amount = float(group["Metrics"]["UnblendedCost"]["Amount"])
                if amount > 0.01:
                    services[service_name] = amount
            results.append(DailyCost(date=date, amount=round(total, 2), services=services))

        return sorted(results, key=lambda x: x.date)
