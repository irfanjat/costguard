output "lambda_function_name" {
  description = "Name of the CostGuard Lambda function"
  value       = aws_lambda_function.costguard.function_name
}

output "lambda_arn" {
  description = "ARN of the CostGuard Lambda function"
  value       = aws_lambda_function.costguard.arn
}

output "schedule_rule_name" {
  description = "EventBridge schedule rule name"
  value       = aws_cloudwatch_event_rule.schedule.name
}

output "dynamodb_table_name" {
  description = "DynamoDB history table name"
  value       = aws_dynamodb_table.history.name
}

output "iam_role_arn" {
  description = "IAM role ARN for the Lambda function"
  value       = aws_iam_role.lambda.arn
}
