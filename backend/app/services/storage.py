import boto3
from botocore.config import Config
from app.core.config import settings

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

    def get_presigned_url(self, object_name: str, expiration: int = 3600):
        """
        Generar una URL prefirmada para subir una imagen directamente a R2.
        """
        if not self.s3_client:
            return None
        
        try:
            response = self.s3_client.generate_presigned_post(
                Bucket=settings.R2_BUCKET_NAME,
                Key=object_name,
                ExpiresIn=expiration
            )
            return response
        except Exception as e:
            # En producción, registrar este error
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
            print("Advertencia: Credenciales R2 no configuradas. Omitiendo subida.")
            return True # Simular que funcionó para desarrollo local si no hay credenciales
        
        try:
            self.s3_client.put_object(
                Bucket=settings.R2_BUCKET_NAME,
                Key=object_name,
                Body=file_content,
                ContentType=content_type
            )
            return True
        except Exception as e:
            print(f"Error subiendo a R2: {e}")
            return False

storage_service = StorageService()
