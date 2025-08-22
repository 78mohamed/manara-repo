# Serverless Image Processing Project

## Overview
This project is a serverless image processing application where users upload images to an S3 bucket. This triggers an AWS Lambda function that processes and resizes the images before storing them in another S3 bucket.

## Architecture
- **Amazon S3**: Two buckets are used, one for original images and another for processed/resized images.
- **AWS Lambda**: Function to process images (resize, watermark).
- **IAM Roles and Policies**: For Lambda execution and S3 access.
- **(Optional) DynamoDB**: A table to store image metadata.
- **(Optional) API Gateway**: Can be added to expose an API for uploads.

## Cost Considerations
This project emphasizes low cost for study purposes by using:
- Pay-per-request billing modes.
- Minimal memory and timeout settings in Lambda.
- No unnecessary resources or over-provisioning.

## Deployment
- Uses Terraform to define infrastructure.
- Uses GitHub Actions for CI/CD to deploy Terraform changes automatically.

## How to Use
1. Upload images to the `original-images-bucket-study` S3 bucket.
2. Lambda automatically processes and stores resized images in the `processed-images-bucket-study` bucket.
3. (Optional) Store metadata in DynamoDB if needed.

## Notes
- API Gateway is optional and not included by default to avoid complexity and cost.
- DynamoDB is optional and only included for metadata storage if required.

## Requirements
- AWS CLI configured with appropriate permissions.
- Terraform installed.
- GitHub repository set up with Terraform files and GitHub Actions workflow.
