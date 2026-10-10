"""campaign audience (multiple groups, picked people, exclusions)

Revision ID: a7c1f0e2b9d4
Revises: 1302886e18bc
Create Date: 2026-10-10 09:00:00
"""
from alembic import op
import sqlalchemy as sa

revision = 'a7c1f0e2b9d4'
down_revision = '1302886e18bc'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('campaigns') as batch_op:
        batch_op.add_column(sa.Column('audience', sa.JSON(), nullable=True))


def downgrade():
    with op.batch_alter_table('campaigns') as batch_op:
        batch_op.drop_column('audience')
