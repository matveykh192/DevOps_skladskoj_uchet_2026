-- Исправленное представление остатков.
-- Приход и расход считаются отдельными подзапросами,
-- чтобы не было декартова произведения.

CREATE OR REPLACE VIEW v_material_balances AS
SELECT
    m.id                                        AS material_id,
    m.name                                      AS material_name,
    mu.short_name                               AS unit_name,
    COALESCE(recv.total_received, 0)            AS total_received,
    COALESCE(iss.total_issued, 0)               AS total_issued,
    COALESCE(recv.total_received, 0)
        - COALESCE(iss.total_issued, 0)         AS current_balance
FROM materials m
LEFT JOIN measurement_units mu
       ON m.measurement_unit_id = mu.id
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