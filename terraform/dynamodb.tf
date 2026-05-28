resource "aws_dynamodb_table" "history" {
  name           = "${var.project_name}-history"
  billing_mode   = "PAY_PER_REQUEST"
  hash_key       = "run_id"

  attribute {
    name = "run_id"
    type = "S"
  }

  attribute {
    name = "timestamp"
    type = "S"
  }

  global_secondary_index {
    name            = "TimestampIndex"
    hash_key        = "timestamp"
    projection_type = "ALL"
  }

  tags = {
    Name        = "${var.project_name}-history"
    Environment = "production"
    ManagedBy   = "terraform"
  }
}
