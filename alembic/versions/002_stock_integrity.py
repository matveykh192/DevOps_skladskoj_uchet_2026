"""002: validate warehouse quantity/price rules at database level."""
from alembic import op

revision = "002_stock_integrity"
down_revision = "001_baseline"
branch_labels = None
depends_on = None

CHECKS = (
    ("materials", "ck_materials_quantity_nonnegative", "quantity >= 0"),
    ("receipt_items", "ck_receipt_items_quantity_positive", "quantity > 0"),
    ("receipt_items", "ck_receipt_items_price_nonnegative", "unit_price >= 0"),
    ("issue_items", "ck_issue_items_quantity_positive", "quantity > 0"),
)


def upgrade():
    # Legacy DB may already have equivalent unnamed CHECK constraints.
    # Named additions are safe on valid data; bad existing data must fail visibly.
    for table, name, condition in CHECKS:
        op.create_check_constraint(name, table, condition)


def downgrade():
    for table, name, _ in reversed(CHECKS):
        op.drop_constraint(name, table, type_="check")
