resource "aws_lambda_function" "costguard" {
  filename         = "${path.module}/../dist/costguard.zip"
  function_name    = "${var.project_name}-handler"
  role             = aws_iam_role.lambda.arn
  handler          = "app.lambda_handler"
  runtime          = "python3.12"
  timeout          = 120
  memory_size      = 256
  source_code_hash = filebase64sha256("${path.module}/../dist/costguard.zip")

  environment {
    variables = {
      COSTGUARD_LOOKBACK_DAYS   = tostring(var.lookback_days)
      COSTGUARD_ZSCORE_THRESHOLD = tostring(var.zscore_threshold)
      COSTGUARD_AUTO_REMEDIATE   = tostring(var.auto_remediate)
      COSTGUARD_REGIONS         = var.regions
      COSTGUARD_HISTORY_TABLE   = aws_dynamodb_table.history.name
      SLACK_WEBHOOK_URL         = var.slack_webhook_url
      COSTGUARD_DASHBOARD_URL   = ""
      COSTGUARD_REMEDIATE_URL   = ""
    }
  }
}

resource "aws_lambda_permission" "events" {
  statement_id  = "AllowExecutionFromEventBridge"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.costguard.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.schedule.arn
}

resource "aws_cloudwatch_log_group" "costguard" {
  name              = "/aws/lambda/${aws_lambda_function.costguard.function_name}"
  retention_in_days = var.lambda_log_retention_days
}
