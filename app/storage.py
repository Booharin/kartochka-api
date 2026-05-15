import boto3
from botocore.config import Config
from app.config import settings

_s3 = None

def get_s3():
    global _s3
    if _s3 is None:
        _s3 = boto3.client(
            's3',
            endpoint_url=settings.r2_endpoint,
            aws_access_key_id=settings.r2_access_key_id,
            aws_secret_access_key=settings.r2_secret_access_key,
            config=Config(signature_version='s3v4'),
            region_name='auto',
        )
    return _s3

def upload_file(file_bytes: bytes, path: str, content_type: str = 'image/jpeg') -> str:
    s3 = get_s3()
    s3.put_object(
        Bucket=settings.r2_bucket,
        Key=path,
        Body=file_bytes,
        ContentType=content_type,
    )
    return f"https://api.kartochka.top/files/{path}"

def get_file(path: str) -> bytes:
    s3 = get_s3()
    response = s3.get_object(Bucket=settings.r2_bucket, Key=path)
    return response['Body'].read()
