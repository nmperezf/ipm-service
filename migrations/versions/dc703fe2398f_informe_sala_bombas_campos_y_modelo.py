"""informe_sala_bombas_campos_y_modelo

Revision ID: dc703fe2398f
Revises: 5662cfc2a91f
Create Date: 2026-08-15 22:55:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'dc703fe2398f'
down_revision = '5662cfc2a91f'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('informes_generados',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('item_visita_id', sa.Integer(), nullable=False),
    sa.Column('categoria', sa.String(length=60), nullable=False),
    sa.Column('numero', sa.String(length=30), nullable=False),
    sa.Column('empresa_id', sa.Integer(), nullable=False),
    sa.Column('dictamen', sa.Text(), nullable=True),
    sa.Column('generado_por_id', sa.Integer(), nullable=True),
    sa.Column('fecha_generacion', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['empresa_id'], ['empresas.id'], ),
    sa.ForeignKeyConstraint(['generado_por_id'], ['usuarios.id'], ),
    sa.ForeignKeyConstraint(['item_visita_id'], ['items_visita.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('item_visita_id', 'categoria', name='uq_informe_item_categoria'),
    sa.UniqueConstraint('numero')
    )
    with op.batch_alter_table('informes_generados', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_informes_generados_empresa_id'), ['empresa_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_informes_generados_generado_por_id'), ['generado_por_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_informes_generados_item_visita_id'), ['item_visita_id'], unique=False)

    with op.batch_alter_table('instalaciones', schema=None) as batch_op:
        batch_op.add_column(sa.Column('aseguradora', sa.String(length=150), nullable=True))
        batch_op.add_column(sa.Column('numero_poliza', sa.String(length=60), nullable=True))
        batch_op.add_column(sa.Column('tag_sala_bombas', sa.String(length=60), nullable=True))

    with op.batch_alter_table('usuarios', schema=None) as batch_op:
        batch_op.add_column(sa.Column('matricula_profesional', sa.String(length=100), nullable=True))

    with op.batch_alter_table('visitas', schema=None) as batch_op:
        batch_op.add_column(sa.Column('nombre_representante_cliente', sa.String(length=150), nullable=True))
        batch_op.add_column(sa.Column('cargo_representante_cliente', sa.String(length=150), nullable=True))
        batch_op.add_column(sa.Column('hora_inicio', sa.Time(), nullable=True))
        batch_op.add_column(sa.Column('hora_termino', sa.Time(), nullable=True))


def downgrade():
    with op.batch_alter_table('visitas', schema=None) as batch_op:
        batch_op.drop_column('hora_termino')
        batch_op.drop_column('hora_inicio')
        batch_op.drop_column('cargo_representante_cliente')
        batch_op.drop_column('nombre_representante_cliente')

    with op.batch_alter_table('usuarios', schema=None) as batch_op:
        batch_op.drop_column('matricula_profesional')

    with op.batch_alter_table('instalaciones', schema=None) as batch_op:
        batch_op.drop_column('tag_sala_bombas')
        batch_op.drop_column('numero_poliza')
        batch_op.drop_column('aseguradora')

    with op.batch_alter_table('informes_generados', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_informes_generados_item_visita_id'))
        batch_op.drop_index(batch_op.f('ix_informes_generados_generado_por_id'))
        batch_op.drop_index(batch_op.f('ix_informes_generados_empresa_id'))

    op.drop_table('informes_generados')
