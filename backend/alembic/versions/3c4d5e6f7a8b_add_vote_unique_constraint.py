"""Add vote unique constraint (dedupe existing rows)

Revision ID: 3c4d5e6f7a8b
Revises: 2b7c8a9d1e2f
Create Date: 2026-08-28 00:00:00.000000

"""

from typing import Sequence, Union

from sqlalchemy import text

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "3c4d5e6f7a8b"
down_revision: Union[str, Sequence[str], None] = "2b7c8a9d1e2f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Antes de crear el índice único, elimina los duplicados existentes
    # (mismo voter + mismo emparejamiento orientado) que pudieran haber quedado
    # por la carrera previa SELECT-then-INSERT. Se conserva el voto con el id
    # más bajo y se descartan los posteriores.
    connection = op.get_bind()
    connection.execute(text(
        """
        DELETE FROM vote
        WHERE id NOT IN (
            SELECT MIN(id)
            FROM vote
            GROUP BY voter_id, winner_id, loser_id
        )
        """
    ))
    op.create_index(
        "uq_vote_voter_winner_loser",
        "vote",
        ["voter_id", "winner_id", "loser_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_vote_voter_winner_loser", table_name="vote")
