-- =============================================================================
-- Схема БД для standalone-развёртывания (ЛР2)
-- Выполняется ОТ ИМЕНИ postgres в БД warehouse_db.
-- Пользователь warehouse_user и БД warehouse_db создаются отдельно.
-- =============================================================================

-- ---------- Роли ----------
CREATE TABLE roles (
    id SERIAL PRIMARY KEY,
    name VARCHAR(50) UNIQUE NOT NULL CHECK (name IN ('admin', 'warehouse_worker'))
);
COMMENT ON TABLE roles IS 'Справочник ролей пользователей';

-- ---------- Пользователи ----------
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(100) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role_id INT NOT NULL REFERENCES roles(id) ON DELETE RESTRICT,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_users_username ON users(username);
COMMENT ON TABLE users IS 'Пользователи системы и данные для авторизации';

-- ---------- Единицы измерения ----------
CREATE TABLE measurement_units (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) UNIQUE NOT NULL,
    short_name VARCHAR(20) UNIQUE NOT NULL,
    description TEXT,
    is_active BOOLEAN DEFAULT TRUE
);
COMMENT ON TABLE measurement_units IS 'Справочник единиц измерения (шт, кг, м и т.д.)';

-- ---------- Поставщики ----------
CREATE TABLE suppliers (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) UNIQUE NOT NULL,
    contact_name VARCHAR(255),
    phone VARCHAR(50),
    email VARCHAR(255),
    address TEXT,
    is_active BOOLEAN DEFAULT TRUE
);
CREATE INDEX idx_suppliers_name ON suppliers(name);
COMMENT ON TABLE suppliers IS 'Справочник поставщиков материалов';

-- ---------- Материалы ----------
CREATE TABLE materials (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) UNIQUE NOT NULL,
    measurement_unit_id INT NOT NULL REFERENCES measurement_units(id) ON DELETE RESTRICT,
    description TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    quantity NUMERIC(12, 3) NOT NULL DEFAULT 0
);
CREATE INDEX idx_materials_name ON materials(name);
COMMENT ON TABLE materials IS 'Справочник материалов с текущим остатком (quantity)';

-- ---------- Поступления ----------
CREATE TABLE receipts (
    id SERIAL PRIMARY KEY,
    receipt_number VARCHAR(50) UNIQUE NOT NULL,
    supplier_id INT NOT NULL REFERENCES suppliers(id) ON DELETE RESTRICT,
    created_by INT REFERENCES users(id) ON DELETE RESTRICT,
    status VARCHAR(20) DEFAULT 'registered'
        CHECK (status IN ('draft', 'registered', 'cancelled')),
    receipt_date DATE NOT NULL DEFAULT CURRENT_DATE,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_receipts_number ON receipts(receipt_number);
CREATE INDEX idx_receipts_supplier ON receipts(supplier_id);
COMMENT ON TABLE receipts IS 'Документы поступления материалов на склад';

CREATE TABLE receipt_items (
    id SERIAL PRIMARY KEY,
    receipt_id INT NOT NULL REFERENCES receipts(id) ON DELETE CASCADE,
    material_id INT NOT NULL REFERENCES materials(id) ON DELETE RESTRICT,
    quantity NUMERIC(12, 3) NOT NULL CHECK (quantity > 0),
    unit_price NUMERIC(12, 2) NOT NULL CHECK (unit_price >= 0),
    UNIQUE (receipt_id, material_id)
);
CREATE INDEX idx_receipt_items_material ON receipt_items(material_id);
COMMENT ON TABLE receipt_items IS 'Позиции документов поступления';

-- ---------- Расход ----------
CREATE TABLE issues (
    id SERIAL PRIMARY KEY,
    issue_number VARCHAR(50) UNIQUE NOT NULL,
    department VARCHAR(255),
    created_by INT REFERENCES users(id) ON DELETE RESTRICT,
    status VARCHAR(20) DEFAULT 'registered'
        CHECK (status IN ('draft', 'registered', 'cancelled')),
    issue_date DATE NOT NULL DEFAULT CURRENT_DATE,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_issues_number ON issues(issue_number);
COMMENT ON TABLE issues IS 'Документы расхода (выдачи) материалов';

CREATE TABLE issue_items (
    id SERIAL PRIMARY KEY,
    issue_id INT NOT NULL REFERENCES issues(id) ON DELETE CASCADE,
    material_id INT NOT NULL REFERENCES materials(id) ON DELETE RESTRICT,
    quantity NUMERIC(12, 3) NOT NULL CHECK (quantity > 0),
    UNIQUE (issue_id, material_id)
);
CREATE INDEX idx_issue_items_material ON issue_items(material_id);
COMMENT ON TABLE issue_items IS 'Позиции документов расхода';

-- ---------- VIEW для остатков ----------
CREATE OR REPLACE VIEW v_material_balances AS
SELECT
    m.id AS material_id,
    m.name AS material_name,
    mu.short_name AS unit_name,
    COALESCE(recv.total_received, 0) AS total_received,
    COALESCE(iss.total_issued, 0) AS total_issued,
    COALESCE(recv.total_received, 0) - COALESCE(iss.total_issued, 0) AS current_balance
FROM materials m
LEFT JOIN measurement_units mu ON m.measurement_unit_id = mu.id
LEFT JOIN (
    SELECT ri.material_id, SUM(ri.quantity) AS total_received
    FROM receipt_items ri
    JOIN receipts r ON ri.receipt_id = r.id
    WHERE r.status = 'registered'
    GROUP BY ri.material_id
) recv ON recv.material_id = m.id
LEFT JOIN (
    SELECT ii.material_id, SUM(ii.quantity) AS total_issued
    FROM issue_items ii
    JOIN issues i ON ii.issue_id = i.id
    WHERE i.status = 'registered'
    GROUP BY ii.material_id
) iss ON iss.material_id = m.id
WHERE m.is_active = TRUE;

COMMENT ON VIEW v_material_balances IS 'Актуальные остатки материалов (Приход - Расход)';

-- ---------- Начальные данные ----------
INSERT INTO roles (name) VALUES ('admin'), ('warehouse_worker');

INSERT INTO measurement_units (name, short_name, description) VALUES
('Штука', 'шт.', 'Единица измерения'),
('Килограмм', 'кг.', 'Весовая единица'),
('Метр', 'м.', 'Длина');

-- ---------- Права для warehouse_user ----------
-- (на случай, если ALTER DEFAULT PRIVILEGES не сработает)
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO warehouse_user;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO warehouse_user;
GRANT SELECT ON v_material_balances TO warehouse_user;