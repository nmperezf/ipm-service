"""curva_fabrica_punto_50_presion_nullable

Revision ID: 9d494009dc74
Revises: dea312812c67
Create Date: 2026-08-12 21:55:05.878791

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '9d494009dc74'
down_revision = 'dea312812c67'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('curvas_fabrica', schema=None) as batch_op:
        batch_op.alter_column('punto_50_presion',
               existing_type=sa.FLOAT(),
               nullable=True)


def downgrade():
    with op.batch_alter_table('curvas_fabrica', schema=None) as batch_op:
        batch_op.alter_column('punto_50_presion',
               existing_type=sa.FLOAT(),
               nullable=False)
