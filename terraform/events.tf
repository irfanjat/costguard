resource "aws_cloudwatch_event_rule" "schedule" {
  name                = "${var.project_name}-daily-run"
  description         = "Triggers CostGuard daily cost analysis"
  schedule_expression = var.schedule_expression
}

resource "aws_cloudwatch_event_target" "lambda" {
  rule      = aws_cloudwatch_event_rule.schedule.name
  target_id = "costguard-lambda"
  arn       = aws_lambda_function.costguard.arn
}
