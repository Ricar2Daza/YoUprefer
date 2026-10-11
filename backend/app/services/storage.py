import logging
import boto3
from botocore.config import Config
from app.core.config import settings

logger = logging.getLogger(__name__)

class StorageService:
    def __init__(self):
        if all([settings.R2_ACCOUNT_ID, settings.R2_ACCESS_KEY_ID, settings.R2_SECRET_ACCESS_KEY]):
            self.s3_client = boto3.client(
                's3',
                endpoint_url=f"https://{settings.R2_ACCOUNT_ID}.r2.cloudflarestorage.com",
                aws_access_key_id=settings.R2_ACCESS_KEY_ID,
                aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY,
                config=Config(signature_version='s3v4'),
                region_name='auto' # R2 usa auto
            )
        else:
            self.s3_client = None

    def get_presigned_put_url(self, object_name: str, content_type: str = "image/jpeg", expiration: int = 600):
        """
        URL prefirmada para subir con PUT directo a R2.
        R2 NO soporta presigned POST (devolvía 501 "Presigned post requests
        are not yet implemented"): la subida desde el navegador usa PUT.
        """
        if not self.s3_client:
            return None

        try:
            return self.s3_client.generate_presigned_url(
                'put_object',
                Params={
                    'Bucket': settings.R2_BUCKET_NAME,
                    'Key': object_name,
                    'ContentType': content_type,
                },
                ExpiresIn=expiration,
                HttpMethod='PUT'
            )
        except Exception:
            return None

    def get_public_url(self, object_name: str):
        """
        Obtener la URL pública del CDN para la imagen.
        """
        if settings.R2_PUBLIC_DOMAIN:
            return f"{settings.R2_PUBLIC_DOMAIN}/{object_name}"
        return None

    def upload_file(self, file_content: bytes, object_name: str, content_type: str = "image/jpeg"):
        """
        Subir archivo directamente a R2 (usado por el endpoint upload-direct).
        """
        if not self.s3_client:
            logger.warning("Credenciais R2 não configuradas. Subida simulada.")
            return True
        
        try:
            self.s3_client.put_object(
                Bucket=settings.R2_BUCKET_NAME,
                Key=object_name,
                Body=file_content,
                ContentType=content_type
            )
            return True
        except Exception as e:
            logger.error("Erro ao subir arquivo para R2", extra={"object_name": object_name, "error": str(e)})
            return False

    def delete_file(self, object_name: str) -> bool:
        if not object_name:
            return True
        if not self.s3_client:
            return True
        try:
            self.s3_client.delete_object(
                Bucket=settings.R2_BUCKET_NAME,
                Key=object_name,
            )
            return True
        except Exception:
            return False

storage_service = StorageService()
