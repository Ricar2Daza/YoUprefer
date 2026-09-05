import logging
import smtplib
from email.message import EmailMessage
from typing import Optional
from urllib.parse import urlencode

from app.core.config import settings

logger = logging.getLogger(__name__)

PASSWORD_RESET_SUBJECT = "Recupera tu contraseña en YoUprefer"
EMAIL_VERIFY_SUBJECT = "Confirma tu correo en YoUprefer"


def build_frontend_url(path: str, query: Optional[dict] = None) -> str:
    """Construye una URL absoluta apuntando al frontend (para enlaces de correo)."""
    base = (settings.FRONTEND_URL or "http://localhost:3000").rstrip("/")
    if query:
        return f"{base}{path}?{urlencode(query)}"
    return f"{base}{path}"


def build_password_reset_url(reset_token: str) -> str:
    return build_frontend_url("/reset-password", {"token": reset_token})


def build_email_verify_url(verification_token: str) -> str:
    return build_frontend_url("/verify-email", {"token": verification_token})


class EmailService:
    """Servicio de envío de correo transaccional.

    Proveedor pluggable controlado por ``settings.EMAIL_PROVIDER``:
      - ``log``   (por defecto): registra el correo renderizado en el log. Perfecto
                  para desarrollo/tesis sin credenciales.
      - ``print`` : imprime el correo en consola.
      - ``smtp``  : envía de verdad vía SMTP (requiere ``SMTP_HOST/USER/PASS``).

    Si ``settings.EMAIL_ENABLED`` es ``False`` no se envía nada. Cualquier error
    de envío se registra y se devuelve ``False`` (best-effort): el flujo de
    negocio (por ejemplo, generar un token de reset) nunca se rompe por un fallo
    de email.
    """

    def _provider(self) -> str:
        return (settings.EMAIL_PROVIDER or "log").lower()

    def email_enabled(self) -> bool:
        return bool(settings.EMAIL_ENABLED)

    # --- render de mensajes -------------------------------------------------

    def _password_reset_body(self, to_email: str, reset_url: str) -> str:
        return (
            "Hola,\n\n"
            "Recibimos una solicitud para restablecer tu contraseña de YoUprefer.\n\n"
            f"Abre el siguiente enlace para crear una nueva contraseña (válido por 1 hora):\n\n"
            f"{reset_url}\n\n"
            "Si no solicitaste este cambio, puedes ignorar este correo.\n\n"
            "— El equipo de YoUprefer"
        )

    def _email_verify_body(self, to_email: str, verify_url: str) -> str:
        return (
            "Hola,\n\n"
            "Gracias por registrarte en YoUprefer. Confirma tu dirección de correo "
            "para activar tu cuenta:\n\n"
            f"{verify_url}\n\n"
            "El enlace es válido por 1 hora.\n\n"
            "— El equipo de YoUprefer"
        )

    # --- proveedores ---------------------------------------------------------

    def _send_log(self, to_email: str, subject: str, body: str) -> bool:
        from_email = settings.EMAIL_FROM or "no-reply@youprefer.local"
        from_name = settings.EMAIL_FROM_NAME or "YoUprefer"
        logger.info(
            "[EMAIL:%s] De: %s <%s>\nAsunto: %s\nPara: %s\n\n%s",
            self._provider(), from_name, from_email, subject, to_email, body,
        )
        return True

    def _send_print(self, to_email: str, subject: str, body: str) -> bool:
        from_email = settings.EMAIL_FROM or "no-reply@youprefer.local"
        from_name = settings.EMAIL_FROM_NAME or "YoUprefer"
        print(
            "=" * 60,
            f"De: {from_name} <{from_email}>",
            f"Asunto: {subject}",
            f"Para: {to_email}",
            "-" * 60,
            body,
            "=" * 60,
            sep="\n",
        )
        return True

    def _send_smtp(self, to_email: str, subject: str, body: str) -> bool:
        host = settings.SMTP_HOST
        user = settings.SMTP_USER
        password = settings.SMTP_PASSWORD
        if not host or not user or not password:
            logger.warning(
                "EMAIL_PROVIDER=smtp pero faltan SMTP_HOST/SMTP_USER/SMTP_PASSWORD. Correo no enviado a %s.",
                to_email,
            )
            return False

        from_email = settings.EMAIL_FROM or "no-reply@youprefer.local"
        from_name = settings.EMAIL_FROM_NAME or "YoUprefer"

        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = f"{from_name} <{from_email}>"
        msg["To"] = to_email
        msg.set_content(body)

        with smtplib.SMTP(host, settings.SMTP_PORT, timeout=10) as server:
            if settings.SMTP_TLS:
                server.starttls()
            server.login(user, password)
            server.send_message(msg)
        return True

    # --- API pública (best-effort) ------------------------------------------

    def send_password_recovery_email(self, to_email: str, reset_token: str) -> bool:
        if not self.email_enabled():
            logger.debug("EMAIL_ENABLED=False; no se envía recovery a %s.", to_email)
            return False
        reset_url = build_password_reset_url(reset_token)
        subject = PASSWORD_RESET_SUBJECT
        body = self._password_reset_body(to_email, reset_url)
        return self._dispatch(to_email, subject, body)

    def send_verification_email(self, to_email: str, verification_token: str) -> bool:
        if not self.email_enabled():
            logger.debug("EMAIL_ENABLED=False; no se envía verificación a %s.", to_email)
            return False
        verify_url = build_email_verify_url(verification_token)
        subject = EMAIL_VERIFY_SUBJECT
        body = self._email_verify_body(to_email, verify_url)
        return self._dispatch(to_email, subject, body)

    def _dispatch(self, to_email: str, subject: str, body: str) -> bool:
        provider = self._provider()
        try:
            if provider == "smtp":
                return self._send_smtp(to_email, subject, body)
            if provider == "print":
                return self._send_print(to_email, subject, body)
            return self._send_log(to_email, subject, body)
        except Exception as e:  # pragma: no cover - defensivo
            logger.error("Error enviando email a %s: %s", to_email, e, exc_info=True)
            return False


email_service = EmailService()
