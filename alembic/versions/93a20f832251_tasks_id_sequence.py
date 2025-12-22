"""tasks id sequence

Revision ID: 93a20f832251
Revises: 0166cc3b9157
Create Date: 2025-12-22 07:20:39.438876

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '93a20f832251'
down_revision: Union[str, Sequence[str], None] = '0166cc3b9157'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    # 1) sequence
    op.execute("CREATE SEQUENCE IF NOT EXISTS tasks_id_seq")

    # 2) default на колонку id
    op.execute("ALTER TABLE tasks ALTER COLUMN id SET DEFAULT nextval('tasks_id_seq')")

    # 3) синхронизировать sequence с текущими данными
    op.execute("""
        SELECT setval('tasks_id_seq',
                      COALESCE((SELECT MAX(id) FROM tasks), 0) + 1,
                      false)
    """)

def downgrade():
    op.execute("ALTER TABLE tasks ALTER COLUMN id DROP DEFAULT")
    op.execute("DROP SEQUENCE IF EXISTS tasks_id_seq")
