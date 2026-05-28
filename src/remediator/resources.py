from __future__ import annotations

import boto3
from pydantic import BaseModel


class OrphanedResource(BaseModel):
    resource_type: str
    resource_id: str
    region: str
    estimated_monthly_cost: float
    reason: str
    age_days: int
    can_auto_remediate: bool
    action: str  # delete, stop, untag, ignore


class RemediationReport(BaseModel):
    total_orphaned_count: int
    total_estimated_savings: float
    resources: list[OrphanedResource]
    auto_remediated_count: int
    auto_remediation_enabled: bool


class ResourceScanner:
    ELIGIBLE_TAGS = {"Environment", "Project", "Owner", "CostCenter"}

    def __init__(
        self,
        session: boto3.Session | None = None,
        regions: list[str] | None = None,
        required_tags: set[str] | None = None,
        auto_remediate: bool = False,
        stale_snapshot_days: int = 90,
    ):
        self.session = session or boto3.Session()
        self.regions = regions or [self.session.region_name or "us-east-1"]
        self.required_tags = required_tags or self.ELIGIBLE_TAGS
        self.auto_remediate = auto_remediate
        self.stale_snapshot_days = stale_snapshot_days

    def scan(self) -> RemediationReport:
        resources: list[OrphanedResource] = []

        for region in self.regions:
            resources.extend(self._scan_unattached_ebs(region))
            resources.extend(self._scan_unassociated_eips(region))
            resources.extend(self._scan_idle_lbs(region))
            resources.extend(self._scan_stale_snapshots(region))

        total_savings = sum(r.estimated_monthly_cost for r in resources)
        auto_count = sum(1 for r in resources if r.can_auto_remediate)

        return RemediationReport(
            total_orphaned_count=len(resources),
            total_estimated_savings=round(total_savings, 2),
            resources=resources,
            auto_remediated_count=auto_count,
            auto_remediation_enabled=self.auto_remediate,
        )

    def _scan_unattached_ebs(self, region: str) -> list[OrphanedResource]:
        ec2 = self.session.client("ec2", region_name=region)
        found: list[OrphanedResource] = []
        paginator = ec2.get_paginator("describe_volumes")
        for page in paginator.paginate(
            Filters=[{"Name": "status", "Values": ["available"]}]
        ):
            for vol in page["Volumes"]:
                found.append(
                    OrphanedResource(
                        resource_type="ebs_volume",
                        resource_id=vol["VolumeId"],
                        region=region,
                        estimated_monthly_cost=round(
                            vol.get("Size", 8) * 0.08, 2
                        ),
                        reason="Unattached EBS volume — not mounted to any instance",
                        age_days=(
                            (
                                __import__("datetime")
                                .datetime.now(__import__("datetime").timezone.utc)
                                - vol["CreateTime"]
                            ).days
                        ),
                        can_auto_remediate=True,
                        action="delete",
                    )
                )
        return found

    def _scan_unassociated_eips(self, region: str) -> list[OrphanedResource]:
        ec2 = self.session.client("ec2", region_name=region)
        found: list[OrphanedResource] = []
        for addr in ec2.describe_addresses().get("Addresses", []):
            if not addr.get("InstanceId") and not addr.get("NetworkInterfaceId"):
                found.append(
                    OrphanedResource(
                        resource_type="eip",
                        resource_id=addr["AllocationId"],
                        region=region,
                        estimated_monthly_cost=3.60,
                        reason="Unassociated Elastic IP — idle public IP incurring hourly cost",
                        age_days=0,
                        can_auto_remediate=True,
                        action="release",
                    )
                )
        return found

    def _scan_idle_lbs(self, region: str) -> list[OrphanedResource]:
        elbv2 = self.session.client("elbv2", region_name=region)
        found: list[OrphanedResource] = []
        lbs = elbv2.describe_load_balancers().get("LoadBalancers", [])
        for lb in lbs:
            lb_arn = lb["LoadBalancerArn"]
            listeners = elbv2.describe_listeners(LoadBalancerArn=lb_arn).get(
                "Listeners", []
            )
            tg_arns = []
            for listener in listeners:
                for action in listener.get("DefaultActions", []):
                    for tg in action.get("ForwardConfig", {}).get("TargetGroups", []):
                        tg_arns.append(tg["TargetGroupArn"])

            total_healthy = 0
            for tg_arn in tg_arns:
                health = elbv2.describe_target_health(TargetGroupArn=tg_arn)
                for desc in health.get("TargetHealthDescriptions", []):
                    if desc["TargetHealth"]["State"] == "healthy":
                        total_healthy += 1

            if total_healthy == 0:
                scheme = lb.get("Scheme", "internal")
                cost = 22.50 if scheme == "application" else 16.20
                found.append(
                    OrphanedResource(
                        resource_type="load_balancer",
                        resource_id=lb["LoadBalancerName"],
                        region=region,
                        estimated_monthly_cost=cost,
                        reason="Idle load balancer — no healthy targets behind listeners",
                        age_days=0,
                        can_auto_remediate=False,
                        action="delete",
                    )
                )
        return found

    def _scan_stale_snapshots(self, region: str) -> list[OrphanedResource]:
        ec2 = self.session.client("ec2", region_name=region)
        found: list[OrphanedResource] = []
        paginator = ec2.get_paginator("describe_snapshots")
        now = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
        for page in paginator.paginate(OwnerIds=["self"]):
            for snap in page.get("Snapshots", []):
                age = (now - snap["StartTime"]).days
                if age >= self.stale_snapshot_days:
                    size_gb = snap.get("VolumeSize", 10)
                    found.append(
                        OrphanedResource(
                            resource_type="snapshot",
                            resource_id=snap["SnapshotId"],
                            region=region,
                            estimated_monthly_cost=round(size_gb * 0.05, 2),
                            reason=f"Stale snapshot — {age} days old, no recent usage",
                            age_days=age,
                            can_auto_remediate=True,
                            action="delete",
                        )
                    )
        return found
