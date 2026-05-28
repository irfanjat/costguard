# CostGuard 🔥

**Serverless AWS cost optimization platform — anomaly detection, orphaned resource scanning, and Slack alerting, all deployed with Terraform.**

CostGuard runs as a scheduled AWS Lambda function that collects daily cost data via the Cost Explorer API, detects anomalous spend patterns using z-score analysis, scans for orphaned resources (unattached EBS volumes, unused EIPs, stale snapshots), and posts a rich Slack report with remediation buttons.

## Architecture

```
                    ┌─────────────────────────┐
                    │   EventBridge Schedule   │
                    │   (every 6 hours)        │
                    └──────────┬──────────────┘
                               │ triggers
                               ▼
                    ┌─────────────────────────┐
                    │    Lambda Function       │
                    │    (CostGuard)           │
                    └────┬──────┬──────┬──────┘
                         │      │      │
                    ┌────┘      │      └──────┐
                    ▼           ▼              ▼
           ┌────────────┐ ┌──────────┐ ┌──────────────┐
           │  Cost       │ │ DynamoDB │ │  AWS Resource │
           │  Explorer   │ │ History  │ │  Scanner     │
           │  API        │ │ Table    │ │  (EC2, EIP,  │
           └────────────┘ └──────────┘ │  snapshots)  │
                                       └──────┬───────┘
                                              │
                                              ▼
                                    ┌──────────────────┐
                                    │   Slack Webhook   │
                                    │   (rich report)   │
                                    └──────────────────┘
```

## Features

- **Cost Collection** — Fetches daily AWS costs per service from Cost Explorer API with configurable lookback window
- **Anomaly Detection** — Z-score based algorithm that flags unusual spend patterns with severity classification (low/medium/high/critical)
- **Resource Scanning** — Detects orphaned resources (unattached EBS volumes, unused Elastic IPs, stale snapshots) with estimated monthly waste
- **Slack Notifications** — Rich Slack message with cost summary, anomaly list, remediation report, and action buttons
- **History Tracking** — Stores every run result in DynamoDB for trend analysis
- **Terraform IaC** — Complete infrastructure defined as code (Lambda, IAM, DynamoDB, EventBridge)

## Quick Start

### Prerequisites

- Python 3.12+
- AWS account with Cost Explorer enabled
- Slack webhook URL
- Terraform 1.6+

### 1. Configure Environment

```bash
export SLACK_WEBHOOK_URL="https://hooks.slack.com/services/..."
export AWS_PROFILE="your-profile"
```

### 2. Deploy Infrastructure

```bash
make deploy-plan    # Review Terraform changes
make deploy         # Package Lambda + Terraform apply
```

### 3. Run Locally

```bash
make install
python demo.py
```

Or invoke the Lambda manually after deploy:

```bash
# Using AWS CLI
aws lambda invoke \
  --function-name costguard \
  --payload '{}' \
  response.json
```

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `SLACK_WEBHOOK_URL` | — | Slack incoming webhook URL (required) |
| `COSTGUARD_LOOKBACK_DAYS` | `14` | Days of cost history to analyze |
| `COSTGUARD_ZSCORE_THRESHOLD` | `2.0` | Z-score threshold for anomaly detection |
| `COSTGUARD_HISTORY_TABLE` | `costguard-history` | DynamoDB table for run history |
| `COSTGUARD_REGIONS` | all | Comma-separated AWS regions to scan |
| `COSTGUARD_AUTO_REMEDIATE` | `false` | Enable automatic resource cleanup |

### Terraform Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `aws_region` | `us-east-1` | AWS region |
| `schedule_expression` | `rate(6 hours)` | EventBridge schedule |
| `slack_webhook_arn` | — | SSM parameter ARN for webhook secret |

## Project Structure

```
├── src/
│   ├── app.py                    # Lambda entrypoint
│   ├── collector/
│   │   └── cost_explorer.py      # AWS Cost Explorer client
│   ├── detector/
│   │   └── anomaly.py            # Z-score anomaly detection
│   ├── notifier/
│   │   └── slack.py              # Slack rich message formatter
│   └── remediator/
│       └── resources.py          # Orphaned resource scanner
├── terraform/
│   ├── main.tf                   # Provider config
│   ├── lambda.tf                 # Lambda function + permissions
│   ├── iam.tf                    # IAM roles and policies
│   ├── dynamodb.tf               # History table
│   ├── events.tf                 # EventBridge schedule
│   └── variables.tf              # Input variables
├── tests/
│   ├── test_detector.py
│   └── test_remediator.py
├── .github/workflows/
│   └── deploy.yml                # CI/CD pipeline
├── Makefile
├── pyproject.toml
└── requirements.txt
```

## CI/CD

On push to `main`, GitHub Actions:
1. Runs lint (ruff) and tests (pytest)
2. Packages Lambda with dependencies
3. Deploys infrastructure with Terraform

## Slack Report Example

```
🔥 CostGuard Report — INCREASING Spend
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📅 7-Day Total:        $1,234.56
📈 Avg Daily:          $176.37
📊 Projected Monthly:  $5,291.10
📉 Previous Month:     $4,100.00
⚠️ Anomalies Found:    3
📉 Std Dev:            $42.18
📈 MoM Change:         +$1,191.10

🔍 Top Cost Anomalies
🔴 2026-05-25 — $312.45 vs $176.37 (z=+3.2, +77.2%)
🟡 2026-05-23 — $267.18 vs $176.37 (z=+2.2, +51.5%)

🧹 Orphaned Resources (4)
💾 ebs-abc123 — $12.00/mo — unattached 14d
🌐 eip-xyz789 — $3.60/mo — unused
📸 snap-456 — $2.15/mo — stale >30d

[📋 View Full Report]  [🚀 Trigger Remediation]
```

## Author

**Irfan Ali** — irfanali.cloud@gmail.com — github.com/irfanjat
