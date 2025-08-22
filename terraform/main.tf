provider "aws" {
  region = "us-east-1"
}

terraform {
  backend "s3" {
    bucket = "devops-project-23082"
    key    = "terraform.tfstate"
    region = "us-east-1"   
  }
}

# Single S3 bucket for both original and processed images
resource "aws_s3_bucket" "image_bucket" {
  bucket = "image-processing-bucket-study"
}

# S3 bucket ACL (using new resource instead of deprecated argument)
resource "aws_s3_bucket_acl" "image_bucket_acl" {
  bucket = aws_s3_bucket.image_bucket.id
  acl    = "private"
}

# IAM role for Lambda
resource "aws_iam_role" "lambda_exec_role" {
  name = "lambda_exec_role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Action = "sts:AssumeRole",
        Effect = "Allow",
        Principal = {
          Service = "lambda.amazonaws.com"
        },
      },
    ],
  })
}

# IAM policy for Lambda to access S3, DynamoDB and CloudWatch
resource "aws_iam_role_policy" "lambda_policy" {
  name = "lambda_s3_policy"
  role = aws_iam_role.lambda_exec_role.id
  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:ListBucket"
        ],
        Effect = "Allow",
        Resource = [
          "${aws_s3_bucket.image_bucket.arn}",
          "${aws_s3_bucket.image_bucket.arn}/*"
        ]
      },
      {
        Action = [
          "dynamodb:PutItem",
          "dynamodb:GetItem",
          "dynamodb:UpdateItem",
          "dynamodb:DeleteItem"
        ],
        Effect = "Allow",
        Resource = aws_dynamodb_table.image_metadata.arn
      },
      {
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ],
        Effect = "Allow",
        Resource = "arn:aws:logs:*:*:*"
      }
    ]
  })
}

# DynamoDB table for image metadata (moved before Lambda to resolve dependency)
resource "aws_dynamodb_table" "image_metadata" {
  name         = "image_metadata"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "image_id"

  attribute {
    name = "image_id"
    type = "S"
  }
}

# Lambda function
resource "aws_lambda_function" "image_processor" {
  filename         = "image_processor.zip"
  function_name    = "image_processor"
  role             = aws_iam_role.lambda_exec_role.arn
  handler          = "lambda_function.lambda_handler"
  source_code_hash = filebase64sha256("image_processor.zip")
  runtime          = "python3.9"
  memory_size      = 512
  timeout          = 15
  environment {
    variables = {
      BUCKET_NAME   = aws_s3_bucket.image_bucket.bucket
      UPLOAD_PREFIX = "uploads/"
      RESIZED_PREFIX = "resized/"
      DDB_TABLE     = aws_dynamodb_table.image_metadata.name
    }
  }
}

# Lambda permission to allow S3 invocation
resource "aws_lambda_permission" "allow_s3_invocation" {
  statement_id  = "AllowS3Invoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.image_processor.function_name
  principal     = "s3.amazonaws.com"
  source_arn    = aws_s3_bucket.image_bucket.arn
}

# S3 bucket notification to trigger Lambda on uploads under uploads/ prefix
resource "aws_s3_bucket_notification" "bucket_notification" {
  bucket = aws_s3_bucket.image_bucket.id

  lambda_function {
    lambda_function_arn = aws_lambda_function.image_processor.arn
    events              = ["s3:ObjectCreated:*"]
    filter_prefix       = "uploads/"
  }

  depends_on = [
    aws_lambda_function.image_processor,
    aws_lambda_permission.allow_s3_invocation
  ]
}

# API Gateway REST API
resource "aws_api_gateway_rest_api" "image_api" {
  name        = "ImageUploadAPI"
  description = "API for uploading images to S3"
}

# API Gateway resource (root + /upload)
resource "aws_api_gateway_resource" "upload_resource" {
  rest_api_id = aws_api_gateway_rest_api.image_api.id
  parent_id   = aws_api_gateway_rest_api.image_api.root_resource_id
  path_part   = "upload"
}

# API Gateway POST method on /upload
resource "aws_api_gateway_method" "post_upload" {
  rest_api_id   = aws_api_gateway_rest_api.image_api.id
  resource_id   = aws_api_gateway_resource.upload_resource.id
  http_method   = "POST"
  authorization = "NONE"
}

# Lambda integration with API Gateway POST /upload
resource "aws_api_gateway_integration" "lambda_integration" {
  rest_api_id             = aws_api_gateway_rest_api.image_api.id
  resource_id             = aws_api_gateway_resource.upload_resource.id
  http_method             = aws_api_gateway_method.post_upload.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = aws_lambda_function.image_processor.invoke_arn
}

# Grant API Gateway permission to invoke Lambda
resource "aws_lambda_permission" "apigw_lambda_permission" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.image_processor.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_api_gateway_rest_api.image_api.execution_arn}/*/*"
}

resource "aws_api_gateway_deployment" "api_deployment" {
  depends_on  = [aws_api_gateway_integration.lambda_integration]
  rest_api_id = aws_api_gateway_rest_api.image_api.id
  triggers = {
    redeployment = sha1(jsonencode([
      aws_api_gateway_rest_api.image_api.body,
      aws_api_gateway_method.post_upload.id,
      aws_api_gateway_integration.lambda_integration.id
    ]))
  }
}

resource "aws_api_gateway_stage" "prod_stage" {
  stage_name    = "prod"
  rest_api_id   = aws_api_gateway_rest_api.image_api.id
  deployment_id = aws_api_gateway_deployment.api_deployment.id

  depends_on = [aws_api_gateway_deployment.api_deployment]
}

# Output the API Gateway URL for testing
output "api_gateway_url" {
  value = "${aws_api_gateway_rest_api.image_api.execution_arn}/prod/upload"
  description = "API Gateway URL for uploading images"
}
