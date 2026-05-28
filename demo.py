#!/usr/bin/env python3
"""
CostGuard Live Demo
Simulates a full pipeline run: collect → detect → remediate → notify
Uses moto for AWS mocking + synthetic cost data with an injected anomaly.
"""

import json
import os
import sys
from datetime import datetime, timezone
from typing import Any

import boto3
from moto import mock_aws

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from src.collector.cost_explorer import DailyCost
from src.detector.anomaly import AnomalyDetector
from src.remediator.resources import ResourceScanner
from src.notifier.slack import SlackNotifier

GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"


def section(title: str):
    print(f"\n{BOLD}{CYAN}{'='*60}{RESET}")
    print(f"{BOLD}{CYAN}  {title}{RESET}")
    print(f"{BOLD}{CYAN}{'='*60}{RESET}\n")


def step(label: str, status: str = "✓"):
    color = GREEN if status == "✓" else RED
    print(f"  {color}{status}{RESET} {label}")


def generate_cost_data() -> list[DailyCost]:
    """Generate 30 days of realistic cost data with an injected spike."""
    base_daily = 45.0  # $45/day baseline
    today = datetime.now(timezone.utc)
    costs: list[DailyCost] = []

    for i in range(30):
        day = today.replace(hour=0, minute=0, second=0, microsecond=0)
        day = day - __import__("datetime").timedelta(days=29 - i)
        date_str = day.strftime("%Y-%m-%d")

        if i == 27:
            amount = 189.42
        elif i == 28:
            amount = 52.30
        else:
            amount = round(base_daily + (i % 7 - 3) * 2.5, 2)

        costs.append(DailyCost(date=date_str, amount=amount, services={
            "AmazonEC2": round(amount * 0.42, 2),
            "AmazonS3": round(amount * 0.18, 2),
            "AWS Lambda": round(amount * 0.12, 2),
            "AmazonRDS": round(amount * 0.28, 2),
        }))

    return costs


def setup_moto_resources():
    """Create orphaned resources in moto mock for the remediator to find."""
    ec2 = boto3.client("ec2", region_name="us-east-1")
    elbv2 = boto3.client("elbv2", region_name="us-east-1")

    vpc = ec2.create_vpc(CidrBlock="10.0.0.0/16")
    vpc_id = vpc["Vpc"]["VpcId"]
    subnet = ec2.create_subnet(VpcId=vpc_id, CidrBlock="10.0.1.0/24")
    subnet_id = subnet["Subnet"]["SubnetId"]

    step(f"Created VPC {vpc_id[:8]}... + subnet {subnet_id[:8]}...")

    ec2.create_volume(AvailabilityZone="us-east-1a", Size=50, VolumeType="gp3")
    step("Created unattached gp3 50GB volume ($4.00/mo)")

    ec2.create_volume(AvailabilityZone="us-east-1a", Size=500, VolumeType="io1", Iops=3000)
    step("Created unattached io1 500GB volume ($125.00/mo)")

    ec2.allocate_address(Domain="vpc")
    step("Created unassociated Elastic IP ($3.60/mo)")

    lb = elbv2.create_load_balancer(Name="idle-alb", Subnets=[subnet_id])["LoadBalancers"][0]
    tg = elbv2.create_target_group(
        Name="idle-tg", Protocol="HTTP", Port=80, VpcId=vpc_id
    )["TargetGroups"][0]
    elbv2.create_listener(
        LoadBalancerArn=lb["LoadBalancerArn"],
        Protocol="HTTP",
        Port=80,
        DefaultActions=[{"Type": "forward", "ForwardConfig": {"TargetGroups": [{"TargetGroupArn": tg["TargetGroupArn"]}]}}],
    )
    step("Created idle ALB with no healthy targets ($22.50/mo)")

    vol_id = ec2.create_volume(AvailabilityZone="us-east-1a", Size=10)["VolumeId"]
    ec2.create_snapshot(Description="stale-snap", VolumeId=vol_id)
    step("Created stale snapshot ($0.50/mo)")


def run_demo():
    print(f"\n{BOLD}{'🔥 CostGuard Live Demo':^60}{RESET}")
    print(f"{'End-to-end cost anomaly detection & remediation pipeline':^60}")
    print(f"{'─'*60}")

    # ── Phase 1: Collect ──
    section("Phase 1: Cost Data Collection")
    cost_data = generate_cost_data()
    step(f"Generated {len(cost_data)} days of cost data")

    total = sum(c.amount for c in cost_data)
    avg = total / len(cost_data)
    last_week = sum(c.amount for c in cost_data[-7:])

    print(f"\n    {'Date':<14} {'Cost':>8}  {'Top Service':<20} {'Amount':>8}")
    print(f"    {'─'*52}")
    for c in cost_data[-10:]:
        top_svc = max(c.services, key=c.services.get)
        print(f"    {c.date:<14} ${c.amount:>6.2f}  {top_svc:<20} ${c.services[top_svc]:>6.2f}")
    print(f"\n    Total (30d): ${total:,.2f}  |  7-day: ${last_week:,.2f}  |  Avg: ${avg:.2f}")

    # ── Phase 2: Detect ──
    section("Phase 2: Anomaly Detection")
    detector = AnomalyDetector(z_score_threshold=2.0)
    report = detector.analyze(cost_data)

    step(f"Daily avg: ${report.avg_daily_cost:.2f}")
    step(f"Std deviation: ${report.std_dev:.2f}")
    step(f"Projected monthly: ${report.projected_monthly_cost:,.2f}")
    step(f"Previous monthly: ${report.previous_monthly_cost:,.2f}")
    step(f"Burn rate direction: {report.burn_rate_direction}")

    print()
    if report.anomalies:
        print(f"    {BOLD}{RED}Anomalies detected: {len(report.anomalies)}{RESET}")
        print(f"    {'─'*52}")
        for a in report.anomalies:
            color = RED if a.severity in ("high", "critical") else YELLOW
            print(f"    {color}▶ {a.date}: ${a.actual_cost:.2f} vs ${a.expected_cost:.2f}  "
                  f"(z={a.z_score:+.1f}, {a.deviation_percent:+.1f}%) — {a.severity.upper()}{RESET}")
    else:
        print(f"    {GREEN}No anomalies detected (threshold z ≥ {detector.z_score_threshold}){RESET}")

    diff = report.projected_monthly_cost - report.previous_monthly_cost
    if diff > 0:
        print(f"\n    {YELLOW}⚠️  Projected increase: +${diff:,.2f}/mo ({diff/report.previous_monthly_cost*100:.1f}%){RESET}")
    else:
        print(f"\n    {GREEN}✅ Projected decrease: {diff:,.2f}/mo{RESET}")

    # ── Phase 3: Remediate ──
    section("Phase 3: Resource Remediation (moto-mocked AWS)")

    with mock_aws():
        setup_moto_resources()
        scanner = ResourceScanner(regions=["us-east-1"])
        remediation = scanner.scan()

    step(f"Total orphaned resources: {remediation.total_orphaned_count}")
    step(f"Estimated monthly waste: ${remediation.total_estimated_savings:.2f}")
    step(f"Auto-remediable resources: {remediation.auto_remediated_count}")

    print()
    if remediation.resources:
        print(f"    {'Type':<18} {'Resource ID':<30} {'Cost/mo':>8}  {'Reason':<40}")
        print(f"    {'─'*96}")
        for r in remediation.resources:
            print(f"    {r.resource_type:<18} {r.resource_id:<30} ${r.estimated_monthly_cost:>6.2f}  {r.reason:<40}")
        print(f"\n    {YELLOW}💸 Total recoverable: ${remediation.total_estimated_savings:.2f}/mo  "
              f"(${remediation.total_estimated_savings * 12:.2f}/yr){RESET}")
    else:
        print(f"    {GREEN}No orphaned resources found{RESET}")

    # ── Phase 4: Notify ──
    section("Phase 4: Slack Notification Payload")

    notifier = SlackNotifier(webhook_url="https://hooks.slack.com/services/TEST/WEBHOOK")
    blocks = notifier._build_blocks(report, remediation)
    payload = {
        "text": f"CostGuard Report: {report.burn_rate_direction.upper()} — ${report.projected_monthly_cost}/mo projected",
        "blocks": blocks,
    }

    print(f"    Payload structure: {len(blocks)} blocks\n")
    for i, block in enumerate(blocks):
        btype = block.get("type", "unknown")
        if btype == "header":
            text = block.get("text", {}).get("text", "")
            print(f"    {GREEN}[{i}] {btype}{RESET}  🔤 {text}")
        elif btype == "section":
            fields = block.get("fields", [])
            text = block.get("text", {}).get("text", "")
            if fields:
                print(f"    {GREEN}[{i}] {btype}{RESET}  📊 {len(fields)} fields")
                for f in fields:
                    t = f.get("text", "")
                    print(f"          {t[:90]}..." if len(t) > 90 else f"          {t}")
            elif text:
                lines = text.split("\n")
                print(f"    {GREEN}[{i}] {btype}{RESET}  📝 {len(lines)} lines")
                for line in lines[:3]:
                    print(f"          {line[:90]}")
                if len(lines) > 3:
                    print(f"          ... and {len(lines)-3} more lines")
        elif btype == "actions":
            print(f"    {GREEN}[{i}] {btype}{RESET}  🎯 {len(block.get('elements', []))} buttons")
        elif btype == "divider":
            print(f"    {GREEN}[{i}] {btype}{RESET}  ─────")
        else:
            print(f"    {GREEN}[{i}] {btype}{RESET}")

    # ── Summary ──
    section("📊 Executive Summary")
    print(f"""
    {BOLD}CostGuard Analysis — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}{RESET}

    {BOLD}Cost Status:{RESET}
      • 7-day total:     ${report.total_cost_last_7_days:,.2f}
      • Projected month: ${report.projected_monthly_cost:,.2f}
      • Previous month:  ${report.previous_monthly_cost:,.2f}
      • Direction:       {report.burn_rate_direction}

    {BOLD}Anomalies: {len(report.anomalies)}{RESET}
""" + "\n".join(
        f"      • {RED if a.severity in ('high','critical') else YELLOW}{a.severity.upper()}: "
        f"${a.actual_cost:.2f} on {a.date} (z={a.z_score:+.1f}){RESET}"
        for a in report.anomalies
    ) + f"""
    {BOLD}Remediation Opportunity:{RESET}
      • {remediation.total_orphaned_count} orphaned resources
      • ${remediation.total_estimated_savings:.2f} recoverable / month
      • ${remediation.total_estimated_savings * 12:.2f} recoverable / year
""")


if __name__ == "__main__":
    run_demo()
