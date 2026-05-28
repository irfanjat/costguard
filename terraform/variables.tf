variable "aws_region" {
  description = "AWS region for CostGuard deployment"
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  description = "Project name used for resource naming"
  type        = string
  default     = "costguard"
}

variable "schedule_expression" {
  description = "EventBridge schedule expression"
  type        = string
  default     = "cron(0 12 * * ? *)"
}

variable "lookback_days" {
  description = "Number of days to look back for cost data"
  type        = number
  default     = 14
}

variable "zscore_threshold" {
  description = "Z-score threshold for anomaly detection"
  type        = number
  default     = 2.0
}

variable "auto_remediate" {
  description = "Enable automatic remediation of orphaned resources"
  type        = bool
  default     = false
}

variable "slack_webhook_url" {
  description = "Slack webhook URL for notifications"
  type        = string
  sensitive  = true
  default     = ""
}

variable "regions" {
  description = "Comma-separated list of regions to scan"
  type        = string
  default     = "us-east-1,us-west-2,eu-west-1"
}

variable "lambda_log_retention_days" {
  description = "CloudWatch log retention for Lambda"
  type        = number
  default     = 14
}
