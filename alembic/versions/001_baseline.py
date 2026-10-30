"""001: initial warehouse schema, for EMPTY database only.

Revision ID: 001_baseline
Revises:
"""
from alembic import op
import sqlalchemy as sa

revision = "001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("roles", sa.Column("id", sa.Integer, primary_key=True), sa.Column("name", sa.String(50), nullable=False, unique=True))
    op.create_table("measurement_units", sa.Column("id", sa.Integer, primary_key=True), sa.Column("name", sa.String(100), nullable=False, unique=True), sa.Column("short_name", sa.String(20), nullable=False, unique=True), sa.Column("description", sa.Text), sa.Column("is_active", sa.Boolean, server_default=sa.true()))
    op.create_table("suppliers", sa.Column("id", sa.Integer, primary_key=True), sa.Column("name", sa.String(255), nullable=False, unique=True), sa.Column("contact_name", sa.String(255)), sa.Column("phone", sa.String(50)), sa.Column("email", sa.String(255)), sa.Column("address", sa.Text), sa.Column("is_active", sa.Boolean, server_default=sa.true()))
    op.create_table("users", sa.Column("id", sa.Integer, primary_key=True), sa.Column("username", sa.String(100), nullable=False, unique=True), sa.Column("password_hash", sa.String(255), nullable=False), sa.Column("role_id", sa.Integer, sa.ForeignKey("roles.id"), nullable=False), sa.Column("is_active", sa.Boolean, server_default=sa.true()), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()))
    op.create_table("materials", sa.Column("id", sa.Integer, primary_key=True), sa.Column("name", sa.String(255), nullable=False, unique=True), sa.Column("measurement_unit_id", sa.Integer, sa.ForeignKey("measurement_units.id"), nullable=False), sa.Column("description", sa.Text), sa.Column("is_active", sa.Boolean, server_default=sa.true()), sa.Column("quantity", sa.Numeric(12, 3), nullable=False, server_default="0"))
    op.create_table("receipts", sa.Column("id", sa.Integer, primary_key=True), sa.Column("receipt_number", sa.String(50), nullable=False, unique=True), sa.Column("supplier_id", sa.Integer, sa.ForeignKey("suppliers.id"), nullable=False), sa.Column("created_by", sa.Integer, sa.ForeignKey("users.id")), sa.Column("status", sa.String(20), server_default="draft"), sa.Column("receipt_date", sa.Date, nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()))
    op.create_table("issues", sa.Column("id", sa.Integer, primary_key=True), sa.Column("issue_number", sa.String(50), nullable=False, unique=True), sa.Column("department", sa.String(255)), sa.Column("created_by", sa.Integer, sa.ForeignKey("users.id")), sa.Column("status", sa.String(20), server_default="draft"), sa.Column("issue_date", sa.Date, nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()))
    op.create_table("receipt_items", sa.Column("id", sa.Integer, primary_key=True), sa.Column("receipt_id", sa.Integer, sa.ForeignKey("receipts.id", ondelete="CASCADE"), nullable=False), sa.Column("material_id", sa.Integer, sa.ForeignKey("materials.id"), nullable=False), sa.Column("quantity", sa.Numeric(12, 3), nullable=False), sa.Column("unit_price", sa.Numeric(12, 2), nullable=False))
    op.create_table("issue_items", sa.Column("id", sa.Integer, primary_key=True), sa.Column("issue_id", sa.Integer, sa.ForeignKey("issues.id", ondelete="CASCADE"), nullable=False), sa.Column("material_id", sa.Integer, sa.ForeignKey("materials.id"), nullable=False), sa.Column("quantity", sa.Numeric(12, 3), nullable=False))
    # The legacy SQL initialization defines this view; keep the same compatibility view.
    op.execute("""CREATE VIEW v_material_balances AS
        SELECT m.id AS material_id, m.name AS material_name, mu.short_name AS unit_name,
          COALESCE(recv.total_received, 0) AS total_received,
          COALESCE(iss.total_issued, 0) AS total_issued,
          COALESCE(recv.total_received, 0) - COALESCE(iss.total_issued, 0) AS current_balance
        FROM materials m
        LEFT JOIN measurement_units mu ON m.measurement_unit_id = mu.id
        LEFT JOIN (SELECT ri.material_id, SUM(ri.quantity) AS total_received FROM receipt_items ri JOIN receipts r ON ri.receipt_id = r.id WHERE r.status = 'registered' GROUP BY ri.material_id) recv ON recv.material_id = m.id
        LEFT JOIN (SELECT ii.material_id, SUM(ii.quantity) AS total_issued FROM issue_items ii JOIN issues i ON ii.issue_id = i.id WHERE i.status = 'registered' GROUP BY ii.material_id) iss ON iss.material_id = m.id
        WHERE m.is_active = TRUE""")


def downgrade():
    op.execute("DROP VIEW IF EXISTS v_material_balances")
    for name in ("issue_items", "receipt_items", "issues", "receipts", "materials", "users", "suppliers", "measurement_units", "roles"):
        op.drop_table(name)
