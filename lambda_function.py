import boto3
import os
import json
import base64
from datetime import datetime
from PIL import Image
from io import BytesIO

s3 = boto3.client('s3')
dynamodb = boto3.resource('dynamodb')

BUCKET_NAME = os.environ['BUCKET_NAME']
UPLOAD_PREFIX = os.environ.get('UPLOAD_PREFIX', 'uploads/')
RESIZED_PREFIX = os.environ.get('RESIZED_PREFIX', 'resized/')
DDB_TABLE = os.environ.get('DDB_TABLE', 'image_metadata')
RESIZE_WIDTH = 800

table = dynamodb.Table(DDB_TABLE)

def process_image(file_name, image_bytes, content_type):
    # Create BytesIO object and ensure we're at the beginning
    image_buffer = BytesIO(image_bytes)
    image_buffer.seek(0)  # CRITICAL: Reset pointer to beginning
    
    with Image.open(image_buffer) as img:
        ratio = RESIZE_WIDTH / float(img.width)
        height = int((float(img.height) * float(ratio)))
        resized_img = img.resize((RESIZE_WIDTH, height), Image.LANCZOS)
        
        buffer = BytesIO()
        # Preserve original format or default to JPEG
        format_to_save = img.format if img.format else 'JPEG'
        resized_img.save(buffer, format=format_to_save)
        buffer.seek(0)
        
        resized_key = f"{RESIZED_PREFIX}{file_name}"
        s3.put_object(Bucket=BUCKET_NAME, Key=resized_key, Body=buffer.getvalue(), ContentType=content_type)
        
        return resized_key, len(buffer.getvalue())

def save_metadata(image_id, original_key, resized_key, size_bytes):
    timestamp = datetime.utcnow().isoformat()
    item = {
        'image_id': image_id,
        'original_key': original_key,
        'resized_key': resized_key,
        'size_bytes': size_bytes,
        'timestamp': timestamp
    }
    table.put_item(Item=item)

def handle_s3_event(event):
    for record in event['Records']:
        key = record['s3']['object']['key']
        if not key.startswith(UPLOAD_PREFIX):
            print(f"Skipping non-upload key: {key}")
            continue

        file_name = key.split('/')[-1]
        response = s3.get_object(Bucket=BUCKET_NAME, Key=key)
        image_content = response['Body'].read()
        content_type = response['ContentType']

        resized_key, size_bytes = process_image(file_name, image_content, content_type)
        save_metadata(file_name, key, resized_key, size_bytes)

def handle_api_event(event):
    try:
        print(f"API Gateway event: {json.dumps(event)}")
        
        body = event.get('body', '')
        is_base64 = event.get('isBase64Encoded', False)
        
        # Handle different content types from API Gateway
        if is_base64:
            print("Decoding base64 encoded body")
            image_bytes = base64.b64decode(body)
        else:
            # API Gateway might send binary data as raw bytes
            if isinstance(body, str):
                print("Body is string, attempting base64 decode")
                try:
                    # Try base64 decode first
                    image_bytes = base64.b64decode(body)
                except Exception as e:
                    print(f"Base64 decode failed: {e}, treating as raw string")
                    # If not base64, treat as raw binary encoded as latin1
                    image_bytes = body.encode('latin1')
            else:
                print("Body is bytes")
                image_bytes = body

        # Get filename from query parameters
        query_params = event.get('queryStringParameters') or {}
        file_name = query_params.get('filename', f'image_{int(datetime.utcnow().timestamp())}.jpg')
        key = f"{UPLOAD_PREFIX}{file_name}"

        print(f"Processing image: {file_name}, size: {len(image_bytes)} bytes")

        # Upload original to S3
        s3.put_object(Bucket=BUCKET_NAME, Key=key, Body=image_bytes, ContentType='image/jpeg')
        print(f"Uploaded original image to {key}")

        # Process and resize image
        resized_key, size_bytes = process_image(file_name, image_bytes, 'image/jpeg')
        save_metadata(file_name, key, resized_key, size_bytes)
        
        print(f"Successfully processed image: {file_name}")

        return {
            'statusCode': 200,
            'body': json.dumps({'message': 'Image uploaded and processed', 'resized_url': f's3://{BUCKET_NAME}/{resized_key}'})
        }
    except Exception as e:
        print(f"Error in handle_api_event: {str(e)}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }

def lambda_handler(event, context):
    try:
        print(f"Lambda invoked with event: {json.dumps(event)}")
        
        if 'Records' in event and event['Records'] and 's3' in event['Records'][0]:
            print("Processing S3 event")
            handle_s3_event(event)
            return {'statusCode': 200, 'body': 'Processed S3 event'}
        else:
            print("Processing API Gateway event")
            return handle_api_event(event)
    except Exception as e:
        print(f"Error in lambda_handler: {str(e)}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }
