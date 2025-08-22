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
RESIZE_WIDTH = 800  # Resize width

table = dynamodb.Table(DDB_TABLE)

def process_image(file_name, image_bytes, content_type):
    with Image.open(BytesIO(image_bytes)) as img:
        ratio = RESIZE_WIDTH / float(img.width)
        height = int((float(img.height) * float(ratio)))
        # Use Image.LANCZOS instead of Image.ANTIALIAS
        resized_img = img.resize((RESIZE_WIDTH, height), Image.LANCZOS)
        
        buffer = BytesIO()
        resized_img.save(buffer, format=img.format)
        buffer.seek(0)
        
        resized_key = f"{RESIZED_PREFIX}{file_name}"
        s3.put_object(Bucket=BUCKET_NAME, Key=resized_key, Body=buffer, ContentType=content_type)
        
        return resized_key, buffer.tell()

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
        body = event.get('body', '')
        is_base64 = event.get('isBase64Encoded', False)
        if is_base64:
            image_bytes = base64.b64decode(body)
        else:
            image_bytes = body.encode('utf-8')

        file_name = event.get('queryStringParameters', {}).get('filename', f'image_{datetime.utcnow().timestamp()}.jpg')
        key = f"{UPLOAD_PREFIX}{file_name}"

        # Upload original to S3
        s3.put_object(Bucket=BUCKET_NAME, Key=key, Body=image_bytes, ContentType='image/jpeg')

        resized_key, size_bytes = process_image(file_name, image_bytes, 'image/jpeg')
        save_metadata(file_name, key, resized_key, size_bytes)

        return {
            'statusCode': 200,
            'body': json.dumps({'message': 'Image uploaded and processed', 'resized_url': f's3://{BUCKET_NAME}/{resized_key}'})
        }
    except Exception as e:
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }

def lambda_handler(event, context):
    try:
        if 'Records' in event and event['Records'] and 's3' in event['Records'][0]:
            # Triggered by S3
            handle_s3_event(event)
            return {'statusCode': 200, 'body': 'Processed S3 event'}
        else:
            # Triggered via API Gateway
            return handle_api_event(event)
    except Exception as e:
        print(f"Error: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }
