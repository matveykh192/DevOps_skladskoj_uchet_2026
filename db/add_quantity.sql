-- Добавляем колонку quantity в materials и заполняем её из истории
ALTER TABLE materials ADD COLUMN IF NOT EXISTS quantity NUMERIC(12, 3) DEFAULT 0 NOT NULL;

-- Заполняем текущие значения из накопленной истории
UPDATE materials m
SET quantity = COALESCE((
    SELECT SUM(ri.quantity) FROM receipt_items ri
    JOIN receipts r ON ri.receipt_id = r.id
    WHERE ri.material_id = m.id AND r.status = 'registered'
), 0)
- COALESCE((
    SELECT SUM(ii.quantity) FROM issue_items ii
    JOIN issues i ON ii.issue_id = i.id
    WHERE ii.material_id = m.id AND i.status = 'registered'
), 0);