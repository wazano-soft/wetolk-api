from datetime import datetime, timezone

import boto3
from botocore.client import Config

from app.core.config import settings

_client = boto3.client(
    "s3",
    endpoint_url=f"https://{settings.r2_account_id}.r2.cloudflarestorage.com",
    aws_access_key_id=settings.r2_access_key_id,
    aws_secret_access_key=settings.r2_secret_access_key,
    region_name="auto",
    config=Config(signature_version="s3v4"),
)

MAX_PDF_SIZE_BYTES = 5 * 1024 * 1024  # RF-02: 5 MB


def cv_key(storage_token: str, ts: str | None = None) -> str:
    ts = ts or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    return f"candidates/{storage_token}/cv/{ts}.pdf"


def create_upload_url(key: str, expires_in: int = 300) -> str:
    # NOTA: un presigned PUT no puede acotar el tamaño del body (eso es
    # solo de presigned POST, vía la condición content-length-range). El
    # límite de 5MB hoy se aplica recién en /api/cv/process, después de
    # subido -- alguien con esta URL puede igual poner un archivo más
    # grande en el bucket. Si esto importa de verdad, migrar a
    # generate_presigned_post con esa condición.
    return _client.generate_presigned_url(
        "put_object",
        Params={
            "Bucket": settings.r2_bucket,
            "Key": key,
            "ContentType": "application/pdf",
        },
        ExpiresIn=expires_in,
    )


def create_download_url(key: str, expires_in: int = 300) -> str:
    return _client.generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.r2_bucket, "Key": key},
        ExpiresIn=expires_in,
    )


def get_object_size(key: str) -> int:
    return _client.head_object(Bucket=settings.r2_bucket, Key=key)["ContentLength"]


def download_object(key: str) -> bytes:
    obj = _client.get_object(Bucket=settings.r2_bucket, Key=key)
    return obj["Body"].read()


def delete_prefix(prefix: str) -> int:
    """Borra todos los objetos bajo un prefijo (RNF-03: borrado de cuenta).
    list_objects_v2 pagina de a 1000 -- delete_objects también tiene un
    límite de 1000 claves por llamada, así que se borra por página."""
    deleted = 0
    paginator = _client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=settings.r2_bucket, Prefix=prefix):
        keys = [{"Key": obj["Key"]} for obj in page.get("Contents", [])]
        if not keys:
            continue
        _client.delete_objects(Bucket=settings.r2_bucket, Delete={"Objects": keys})
        deleted += len(keys)
    return deleted
