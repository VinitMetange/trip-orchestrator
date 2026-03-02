# Terraform Variables for TripOrchestrator

variable "aws_region" {
  description = "AWS region for all resources"
  type        = string
  default     = "ap-south-1"
}

variable "bedrock_region" {
  description = "AWS region for Bedrock (Claude 3.5 may be available in specific regions)"
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Deployment environment (development, staging, production)"
  type        = string
  default     = "production"

  validation {
    condition     = contains(["development", "staging", "production"], var.environment)
    error_message = "Environment must be development, staging, or production."
  }
}

variable "lambda_memory_mb" {
  description = "Lambda function memory allocation in MB"
  type        = number
  default     = 1024

  validation {
    condition     = var.lambda_memory_mb >= 512 && var.lambda_memory_mb <= 10240
    error_message = "Lambda memory must be between 512 and 10240 MB."
  }
}

variable "lambda_timeout_seconds" {
  description = "Lambda function timeout in seconds"
  type        = number
  default     = 30
}

variable "lambda_reserved_concurrency" {
  description = "Reserved concurrent executions for Lambda"
  type        = number
  default     = 10000
}

variable "dynamodb_table_name" {
  description = "DynamoDB table name for trip state"
  type        = string
  default     = "trip-orchestrator-trips"
}

variable "log_retention_days" {
  description = "CloudWatch log retention in days"
  type        = number
  default     = 30
}

variable "alert_email" {
  description = "Email address for CloudWatch alarm notifications"
  type        = string
  default     = ""
}

variable "ecr_image_tag" {
  description = "Docker image tag to deploy"
  type        = string
  default     = "latest"
}
