# Importar todos los modelos para que Base los tenga antes de ser
# importados por Alembic
from app.db.base_class import Base  # noqa
from app.models.user import User  # noqa
from app.models.profile import Profile  # noqa
from app.models.category import Category  # noqa
from app.models.vote import Vote  # noqa
from app.models.follow import Follow  # noqa
from app.models.notification import Notification  # noqa
from app.models.badge import Badge, UserBadge  # noqa
from app.models.report import Report  # noqa
from app.models.comment import Comment  # noqa
