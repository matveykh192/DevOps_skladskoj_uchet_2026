"""003: independent minimum-stock threshold per material."""
from alembic import op
import sqlalchemy as sa

revision = "003_minimum_stock"
down_revision = "002_stock_integrity"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("materials", sa.Column("minimum_stock", sa.Numeric(12, 3), nullable=False, server_default="0"))
    op.create_check_constraint("ck_materials_minimum_stock_nonnegative", "materials", "minimum_stock >= 0")


def downgrade():
    op.drop_constraint("ck_materials_minimum_stock_nonnegative", "materials", type_="check")
    op.drop_column("materials", "minimum_stock")
