# Import all the models so that Base has them before being
# imported by Alembic
from app.db.base_class import Base  # noqa
from app.models.user import User  # noqa
from app.models.profile import Profile  # noqa
from app.models.category import Category  # noqa
from app.models.vote import Vote  # noqa
