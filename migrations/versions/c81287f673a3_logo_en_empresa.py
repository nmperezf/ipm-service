"""logo en Empresa

Revision ID: c81287f673a3
Revises: 962f0924f144
Create Date: 2026-08-18 22:01:41.440463

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c81287f673a3'
down_revision = '962f0924f144'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('empresas', schema=None) as batch_op:
        batch_op.add_column(sa.Column('logo', sa.String(length=300), nullable=True))


def downgrade():
    with op.batch_alter_table('empresas', schema=None) as batch_op:
        batch_op.drop_column('logo')
