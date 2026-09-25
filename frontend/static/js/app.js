const API_BASE_URL = 'http://localhost:8000';

// ==========================================
// АВТОРИЗАЦИЯ
// ==========================================
const Auth = {
    getStorage(key) {
        try { return localStorage.getItem(key) || sessionStorage.getItem(key); } catch (e) { return null; }
    },
    setStorage(key, value) {
        try { localStorage.setItem(key, value); } catch (e) {}
        try { sessionStorage.setItem(key, value); } catch (e) {}
    },
    removeStorage(key) {
        try { localStorage.removeItem(key); } catch (e) {}
        try { sessionStorage.removeItem(key); } catch (e) {}
    },
    getToken() { return this.getStorage('auth_token'); },
    getUser() {
        return {
            username: this.getStorage('username') || 'Кладовщик',
            role: this.getStorage('user_role') || 'storekeeper'
        };
    },
    setSession(token, username = 'Кладовщик', role = 'storekeeper') {
        this.setStorage('auth_token', token);
        this.setStorage('username', username);
        this.setStorage('user_role', role);
    },
    clearSession() {
        this.removeStorage('auth_token');
        this.removeStorage('username');
        this.removeStorage('user_role');
    },
    isAuthenticated() { return Boolean(this.getToken()); },
    checkAuth(isLoginPage = false) {
        if (!this.isAuthenticated() && !isLoginPage) window.location.href = '/login';
    },
    logout() { this.clearSession(); window.location.href = '/login'; }
};

// ==========================================
// УТИЛИТЫ
// ==========================================
const UI = {
    showAlert(containerId, message, type = 'danger') {
        const container = document.getElementById(containerId);
        if (!container) return;
        container.innerHTML = `<div class="alert alert-${type} alert-dismissible fade show"><div>${message}</div><button type="button" class="btn-close" data-bs-dismiss="alert"></button></div>`;
    },
    clearAlert(containerId) {
        const container = document.getElementById(containerId);
        if (container) container.innerHTML = '';
    },
    setButtonLoading(btn, isLoading, loadingText = 'Сохранение...') {
        if (!btn) return;
        if (isLoading) {
            btn.dataset.origText = btn.innerHTML;
            btn.disabled = true;
            btn.innerHTML = `<span class="spinner-border spinner-border-sm me-2"></span>${loadingText}`;
        } else {
            btn.disabled = false;
            btn.innerHTML = btn.dataset.origText || 'Сохранить';
        }
    }
};

function escapeHtml(str) {
    if (typeof str !== 'string') return str;
    return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#039;');
}

async function apiFetch(url, options = {}) {
    const res = await fetch(url, options);
    if (res.status === 401) {
        Auth.logout();
        throw new Error('unauthorized');
    }
    return res;
}

// ==========================================
// ВХОД
// ==========================================
function initLoginPage() {
    const loginForm = document.getElementById('loginForm');
    if (!loginForm) return;

    const submitBtn = document.getElementById('loginSubmitBtn');
    const alertBox = 'loginAlert';
    const usernameInput = document.getElementById('username');
    const passwordInput = document.getElementById('password');

    loginForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        UI.clearAlert(alertBox);

        const username = usernameInput.value.trim();
        const password = passwordInput.value.trim();

        if (!username || !password) {
            UI.showAlert(alertBox, 'Введите логин и пароль', 'danger');
            return;
        }

        UI.setButtonLoading(submitBtn, true, 'Вход...');
        const userRole = (username.toLowerCase() === 'admin') ? 'admin' : 'storekeeper';

        try {
            const formData = new URLSearchParams();
            formData.append('username', username);
            formData.append('password', password);

            const response = await fetch(`${API_BASE_URL}/auth/login`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
                body: formData.toString()
            });

            if (response.ok) {
                const data = await response.json();
                Auth.setSession(data.access_token, username, userRole);
                window.location.href = '/materials';
            } else {
                let errorMsg = 'Неверный логин или пароль';
                try {
                    const errData = await response.json();
                    if (typeof errData.detail === 'string') errorMsg = errData.detail;
                } catch (e) {}
                UI.showAlert(alertBox, errorMsg, 'danger');
            }
        } catch (error) {
            console.error('[login]', error);
            UI.showAlert(alertBox, 'Ошибка подключения к серверу', 'danger');
        } finally {
            UI.setButtonLoading(submitBtn, false);
        }
    });
}

// ==========================================
// МАТЕРИАЛЫ
// ==========================================
let allMaterialsCache = [];

async function loadMaterials() {
    const tableBody = document.getElementById('materialsTableBody');
    const loadingState = document.getElementById('materialsLoading');
    const emptyState = document.getElementById('materialsEmpty');
    const titleText = document.getElementById('materialsTitleText');

    if (!tableBody) return;

    if (loadingState) loadingState.classList.remove('d-none');
    if (emptyState) emptyState.classList.add('d-none');
    if (titleText) titleText.textContent = 'Склад';
    tableBody.innerHTML = '';

    try {
        const res = await apiFetch(`${API_BASE_URL}/materials/`, {
            headers: { 'Authorization': `Bearer ${Auth.getToken()}` }
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);

        const materials = await res.json();
        allMaterialsCache = materials;
        renderMaterialsTable(materials);
    } catch (e) {
        if (e.message !== 'unauthorized') {
            console.error('[materials]', e);
            UI.showAlert('materialsAlert', 'Не удалось загрузить материалы', 'danger');
        }
    } finally {
        if (loadingState) loadingState.classList.add('d-none');
    }
}

async function loadLowStockMaterials() {
    const tableBody = document.getElementById('materialsTableBody');
    const loadingState = document.getElementById('materialsLoading');
    const emptyState = document.getElementById('materialsEmpty');
    const titleText = document.getElementById('materialsTitleText');
    const thresholdInput = document.getElementById('lowStockThreshold');

    if (!tableBody) return;

    const threshold = parseFloat(thresholdInput.value);
    if (isNaN(threshold) || threshold < 0) {
        UI.showAlert('materialsAlert', 'Введите корректный порог (число ≥ 0)', 'danger');
        return;
    }

    if (loadingState) loadingState.classList.remove('d-none');
    if (emptyState) emptyState.classList.add('d-none');
    tableBody.innerHTML = '';
    UI.clearAlert('materialsAlert');

    try {
        const res = await apiFetch(`${API_BASE_URL}/materials/low-stock?threshold=${threshold}`, {
            headers: { 'Authorization': `Bearer ${Auth.getToken()}` }
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);

        const data = await res.json();
        if (titleText) titleText.textContent = `Мало на складе (порог: ${data.threshold})`;

        if (!data.items || data.items.length === 0) {
            if (emptyState) {
                emptyState.textContent = `Материалов с остатком ниже ${data.threshold} нет.`;
                emptyState.classList.remove('d-none');
            }
            const counter = document.getElementById('materialsCount');
            if (counter) counter.textContent = 0;
            return;
        }

        renderMaterialsTable(data.items, true);
    } catch (e) {
        if (e.message !== 'unauthorized') {
            console.error('[low-stock]', e);
            UI.showAlert('materialsAlert', 'Не удалось загрузить отчёт', 'danger');
        }
    } finally {
        if (loadingState) loadingState.classList.add('d-none');
    }
}

function renderMaterialsTable(materials, lowStockMode = false) {
    const tableBody = document.getElementById('materialsTableBody');
    const emptyState = document.getElementById('materialsEmpty');
    const counterBadge = document.getElementById('materialsCount');

    if (!tableBody) return;
    tableBody.innerHTML = '';

    if (counterBadge) counterBadge.textContent = materials.length;

    if (!materials || materials.length === 0) {
        if (!lowStockMode && emptyState) {
            emptyState.textContent = 'Материалов пока нет. Создайте поступление.';
            emptyState.classList.remove('d-none');
        }
        return;
    }
    if (emptyState) emptyState.classList.add('d-none');

    const units = { 1: 'шт.', 2: 'кг.', 3: 'м.' };

    materials.forEach(m => {
        const tr = document.createElement('tr');
        const unitName = units[m.measurement_unit_id] || 'шт.';
        const qtyClass = lowStockMode ? 'fw-bold text-danger' : 'fw-bold text-primary';

        tr.innerHTML = `
            <td>${m.id}</td>
            <td class="fw-bold">${escapeHtml(m.name)}</td>
            <td>${unitName}</td>
            <td class="${qtyClass}">${m.quantity || 0} ${unitName}</td>
            <td>${escapeHtml(m.description || '—')}</td>
            <td>
                <button class="btn btn-sm btn-outline-primary me-1" onclick="openEditMaterial(${m.id})" title="Редактировать">✏️</button>
                <button class="btn btn-sm btn-outline-danger" onclick="deleteMaterial(${m.id}, '${escapeHtml(m.name)}')" title="Удалить">🗑</button>
            </td>
        `;
        tableBody.appendChild(tr);
    });
}

async function openEditMaterial(id) {
    try {
        const res = await apiFetch(`${API_BASE_URL}/materials/${id}`, {
            headers: { 'Authorization': `Bearer ${Auth.getToken()}` }
        });
        if (!res.ok) { alert('Материал не найден'); return; }
        const m = await res.json();

        document.getElementById('editMaterialId').value = m.id;
        document.getElementById('editMaterialName').value = m.name;
        document.getElementById('editMaterialUnit').value = m.measurement_unit_id || 1;
        document.getElementById('editMaterialDesc').value = m.description || '';

        const modal = new bootstrap.Modal(document.getElementById('editMaterialModal'));
        modal.show();
    } catch (e) {
        if (e.message !== 'unauthorized') console.error('[edit material]', e);
    }
}
window.openEditMaterial = openEditMaterial;

async function deleteMaterial(id, name) {
    if (!confirm(`Удалить материал «${name}»?\n\nЕсли по нему есть движения (поступления/расходы), удаление будет отклонено.`)) return;

    try {
        const res = await apiFetch(`${API_BASE_URL}/materials/${id}`, {
            method: 'DELETE',
            headers: { 'Authorization': `Bearer ${Auth.getToken()}` }
        });

        if (res.ok) {
            UI.showAlert('materialsAlert', `Материал «${escapeHtml(name)}» удалён`, 'success');
            loadMaterials();
        } else {
            let errMsg = `Ошибка ${res.status}`;
            try {
                const err = await res.json();
                if (typeof err.detail === 'string') errMsg = err.detail;
            } catch (e) {}
            UI.showAlert('materialsAlert', errMsg, 'danger');
        }
    } catch (e) {
        if (e.message !== 'unauthorized') {
            console.error('[delete material]', e);
            UI.showAlert('materialsAlert', 'Ошибка сети', 'danger');
        }
    }
}
window.deleteMaterial = deleteMaterial;

function initMaterialsPage() {
    Auth.checkAuth();
    loadMaterials();

    const lowStockBtn = document.getElementById('showLowStockBtn');
    if (lowStockBtn) {
        lowStockBtn.addEventListener('click', loadLowStockMaterials);
    }

    const showAllBtn = document.getElementById('showAllMaterialsBtn');
    if (showAllBtn) {
        showAllBtn.addEventListener('click', loadMaterials);
    }

    const form = document.getElementById('editMaterialForm');
    if (form) {
        form.addEventListener('submit', async (e) => {
            e.preventDefault();
            UI.clearAlert('modalMaterialAlert');

            const id = document.getElementById('editMaterialId').value;
            const name = document.getElementById('editMaterialName').value.trim();
            const unitId = parseInt(document.getElementById('editMaterialUnit').value);
            const description = document.getElementById('editMaterialDesc').value.trim();

            if (!name) {
                UI.showAlert('modalMaterialAlert', 'Введите название', 'danger');
                return;
            }

            const btn = document.getElementById('saveMaterialBtn');
            UI.setButtonLoading(btn, true, 'Сохранение...');

            try {
                const res = await apiFetch(`${API_BASE_URL}/materials/${id}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${Auth.getToken()}` },
                    body: JSON.stringify({ name, measurement_unit_id: unitId, description })
                });

                if (res.ok) {
                    const modalEl = document.getElementById('editMaterialModal');
                    const modal = bootstrap.Modal.getInstance(modalEl);
                    if (modal) modal.hide();

                    UI.showAlert('materialsAlert', 'Материал сохранён', 'success');
                    loadMaterials();
                } else {
                    let errMsg = `Ошибка ${res.status}`;
                    try {
                        const err = await res.json();
                        if (typeof err.detail === 'string') errMsg = err.detail;
                    } catch (e) {}
                    UI.showAlert('modalMaterialAlert', errMsg, 'danger');
                }
            } catch (e) {
                if (e.message !== 'unauthorized') {
                    console.error('[save material]', e);
                    UI.showAlert('modalMaterialAlert', 'Ошибка сети', 'danger');
                }
            } finally {
                UI.setButtonLoading(btn, false);
            }
        });
    }
}

// ==========================================
// ПОСТУПЛЕНИЯ
// ==========================================
let pendingItems = [];
let receiptsCache = [];
let currentReceiptId = null;

function initReceiptsPage() {
    Auth.checkAuth();
    loadReceiptsList();

    const btnAdd = document.getElementById('btnAddReceiptItem');
    if (btnAdd) {
        btnAdd.addEventListener('click', () => {
            const name = document.getElementById('newMatName').value.trim();
            const unit = parseInt(document.getElementById('newMatUnit').value);
            const qty = parseFloat(document.getElementById('newMatQty').value);
            const price = parseFloat(document.getElementById('newMatPrice').value) || 0;

            if (!name || !qty) { alert('Введите название и количество'); return; }

            pendingItems.push({ material_name: name, measurement_unit_id: unit, quantity: qty, unit_price: price });
            renderPendingItems();

            document.getElementById('newMatName').value = '';
            document.getElementById('newMatQty').value = '';
            document.getElementById('newMatPrice').value = '';
        });
    }

    const form = document.getElementById('addReceiptForm');
    if (form) {
        form.addEventListener('submit', async (e) => {
            e.preventDefault();
            if (pendingItems.length === 0) { alert('Добавьте хотя бы одну позицию'); return; }

            const numberInput = document.getElementById('receiptNumber');
            if (!numberInput.value.trim()) { alert('Введите номер документа'); return; }

            const data = {
                receipt_number: numberInput.value.trim(),
                receipt_date: document.getElementById('receiptDate').value,
                supplier_name: document.getElementById('receiptSupplier').value,
                items: pendingItems
            };

            const btn = document.getElementById('saveReceiptBtn');
            UI.setButtonLoading(btn, true, 'Сохранение...');

            try {
                const res = await apiFetch(`${API_BASE_URL}/receipts/`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${Auth.getToken()}` },
                    body: JSON.stringify(data)
                });

                if (res.ok) {
                    pendingItems = [];
                    form.reset();
                    renderPendingItems();
                    const modal = bootstrap.Modal.getInstance(document.getElementById('addReceiptModal'));
                    if (modal) modal.hide();
                    UI.showAlert('receiptsAlert', 'Поступление успешно зарегистрировано!', 'success');
                    loadReceiptsList();
                } else {
                    let errMsg = `Ошибка ${res.status}`;
                    try {
                        const err = await res.json();
                        if (typeof err.detail === 'string') errMsg = err.detail;
                    } catch (e) {}
                    alert(errMsg);
                }
            } catch (e) {
                if (e.message !== 'unauthorized') {
                    console.error('[receipts]', e);
                    alert('Ошибка сети');
                }
            } finally {
                UI.setButtonLoading(btn, false);
            }
        });
    }

    const delBtn = document.getElementById('deleteReceiptBtn');
    if (delBtn) {
        delBtn.addEventListener('click', async () => {
            if (!currentReceiptId) return;
            const num = document.getElementById('viewReceiptNumber').textContent;
            if (!confirm(`Удалить накладную ${num}?\n\nОстатки материалов будут уменьшены на позиции этой накладной.`)) return;

            delBtn.disabled = true;
            delBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Удаление...';

            try {
                const res = await apiFetch(`${API_BASE_URL}/receipts/${currentReceiptId}`, {
                    method: 'DELETE',
                    headers: { 'Authorization': `Bearer ${Auth.getToken()}` }
                });

                if (res.ok) {
                    const modalEl = document.getElementById('viewReceiptModal');
                    const modal = bootstrap.Modal.getInstance(modalEl);
                    if (modal) modal.hide();

                    UI.showAlert('receiptsAlert', 'Поступление удалено', 'success');
                    loadReceiptsList();
                } else {
                    let errMsg = `Ошибка ${res.status}`;
                    try {
                        const err = await res.json();
                        if (typeof err.detail === 'string') errMsg = err.detail;
                    } catch (e) {}
                    alert(errMsg);
                }
            } catch (e) {
                if (e.message !== 'unauthorized') console.error('[delete receipt]', e);
            } finally {
                delBtn.disabled = false;
                delBtn.innerHTML = '🗑 Удалить накладную';
            }
        });
    }
}

function renderPendingItems() {
    const list = document.getElementById('pendingItemsList');
    if (!list) return;
    if (pendingItems.length === 0) {
        list.innerHTML = '<li class="list-group-item text-muted text-center small">Позиции не добавлены</li>';
        return;
    }
    list.innerHTML = pendingItems.map((item, idx) =>
        `<li class="list-group-item d-flex justify-content-between align-items-center small">
            <span><b>${escapeHtml(item.material_name)}</b> — ${item.quantity} (${item.unit_price} ₽)</span>
            <button type="button" class="btn btn-sm btn-outline-danger border-0" onclick="removePendingItem(${idx})">✕</button>
        </li>`
    ).join('');
}
window.removePendingItem = (idx) => { pendingItems.splice(idx, 1); renderPendingItems(); };

async function loadReceiptsList() {
    const tbody = document.getElementById('receiptsTableBody');
    if (!tbody) return;
    try {
        const res = await apiFetch(`${API_BASE_URL}/receipts/`, {
            headers: { 'Authorization': `Bearer ${Auth.getToken()}` }
        });
        const data = await res.json();
        receiptsCache = data;

        tbody.innerHTML = data.map(r => `
            <tr style="cursor: pointer;" onclick="openViewReceipt(${r.id})">
                <td class="fw-semibold">${escapeHtml(r.receipt_number)}</td>
                <td>Поставщик #${r.supplier_id || '—'}</td>
                <td>${escapeHtml(r.receipt_date)}</td>
                <td class="text-center">${r.items ? r.items.length : 0}</td>
                <td class="text-end fw-semibold">${(r.total_amount || 0).toFixed(2)} ₽</td>
                <td><span class="badge bg-success">${escapeHtml(r.status)}</span></td>
            </tr>
        `).join('');
    } catch (e) {
        if (e.message !== 'unauthorized') console.error('[receipts list]', e);
    }
}

function openViewReceipt(id) {
    const r = receiptsCache.find(x => x.id === id);
    if (!r) return;

    currentReceiptId = r.id;
    document.getElementById('viewReceiptNumber').textContent = r.receipt_number;
    document.getElementById('viewReceiptDate').textContent = r.receipt_date;
    document.getElementById('viewReceiptStatus').textContent = r.status;

    const tbody = document.getElementById('viewReceiptItemsBody');
    if (!r.items || r.items.length === 0) {
        tbody.innerHTML = '<tr><td colspan="4" class="text-center text-muted">Нет позиций</td></tr>';
    } else {
        tbody.innerHTML = r.items.map(item => `
            <tr>
                <td>${escapeHtml(item.material_name || ('#' + item.material_id))}</td>
                <td class="text-end">${item.quantity}</td>
                <td class="text-end">${Number(item.unit_price).toFixed(2)} ₽</td>
                <td class="text-end fw-semibold">${Number(item.line_total || item.quantity * item.unit_price).toFixed(2)} ₽</td>
            </tr>
        `).join('');
    }
    document.getElementById('viewReceiptTotal').textContent = (r.total_amount || 0).toFixed(2) + ' ₽';

    const modal = new bootstrap.Modal(document.getElementById('viewReceiptModal'));
    modal.show();
}
window.openViewReceipt = openViewReceipt;

// ==========================================
// РАСХОД
// ==========================================
let issuesCache = [];
let currentIssueId = null;

async function loadMaterialsForSelect() {
    const select = document.getElementById('issueMaterialId');
    if (!select) return;
    try {
        const res = await apiFetch(`${API_BASE_URL}/materials/`, {
            headers: { 'Authorization': `Bearer ${Auth.getToken()}` }
        });
        const mats = await res.json();

        if (!mats || mats.length === 0) {
            select.innerHTML = '<option value="">Нет материалов на складе</option>';
            return;
        }

        select.innerHTML = '<option value="">Выберите материал...</option>' +
            mats.map(m => `<option value="${m.id}">${escapeHtml(m.name)} (Остаток: ${m.quantity || 0})</option>`).join('');
    } catch (e) {
        if (e.message !== 'unauthorized') {
            console.error('[issues select]', e);
            select.innerHTML = '<option value="">Ошибка загрузки</option>';
        }
    }
}

async function loadIssuesList() {
    const tbody = document.getElementById('issuesTableBody');
    if (!tbody) return;
    try {
        const res = await apiFetch(`${API_BASE_URL}/issues/`, {
            headers: { 'Authorization': `Bearer ${Auth.getToken()}` }
        });
        const data = await res.json();
        issuesCache = data;

        tbody.innerHTML = data.map(i => `
            <tr style="cursor: pointer;" onclick="openViewIssue(${i.id})">
                <td class="fw-semibold">${escapeHtml(i.issue_number)}</td>
                <td>${escapeHtml(i.department || '—')}</td>
                <td>${escapeHtml(i.issue_date)}</td>
                <td class="text-center">${i.items ? i.items.length : 0}</td>
                <td><span class="badge bg-success">${escapeHtml(i.status)}</span></td>
            </tr>
        `).join('');
    } catch (e) {
        if (e.message !== 'unauthorized') console.error('[issues list]', e);
    }
}

function openViewIssue(id) {
    const i = issuesCache.find(x => x.id === id);
    if (!i) return;

    currentIssueId = i.id;
    document.getElementById('viewIssueNumber').textContent = i.issue_number;
    document.getElementById('viewIssueDept').textContent = i.department || '—';
    document.getElementById('viewIssueDate').textContent = i.issue_date;

    const tbody = document.getElementById('viewIssueItemsBody');
    if (!i.items || i.items.length === 0) {
        tbody.innerHTML = '<tr><td colspan="2" class="text-center text-muted">Нет позиций</td></tr>';
    } else {
        tbody.innerHTML = i.items.map(item => `
            <tr>
                <td>${escapeHtml(item.material_name || ('#' + item.material_id))}</td>
                <td class="text-end fw-semibold">${item.quantity}</td>
            </tr>
        `).join('');
    }

    const modal = new bootstrap.Modal(document.getElementById('viewIssueModal'));
    modal.show();
}
window.openViewIssue = openViewIssue;

function initIssuesPage() {
    Auth.checkAuth();
    loadMaterialsForSelect();
    loadIssuesList();

    const form = document.getElementById('addIssueForm');
    if (form) {
        form.addEventListener('submit', async (e) => {
            e.preventDefault();
            UI.clearAlert('modalIssueAlert');

            const numberInput = document.getElementById('issueNumber');
            const deptInput = document.getElementById('issueDept');
            const dateInput = document.getElementById('issueDate');
            const materialSelect = document.getElementById('issueMaterialId');
            const qtyInput = document.getElementById('issueQty');

            if (!numberInput.value.trim()) { UI.showAlert('modalIssueAlert', 'Введите номер документа', 'danger'); return; }
            if (!deptInput.value.trim()) { UI.showAlert('modalIssueAlert', 'Введите подразделение', 'danger'); return; }
            if (!materialSelect.value) { UI.showAlert('modalIssueAlert', 'Выберите материал', 'danger'); return; }

            const qty = parseFloat(qtyInput.value);
            if (!qty || qty <= 0) { UI.showAlert('modalIssueAlert', 'Введите количество', 'danger'); return; }

            const data = {
                issue_number: numberInput.value.trim(),
                department: deptInput.value.trim(),
                issue_date: dateInput.value,
                items: [{ material_id: parseInt(materialSelect.value), quantity: qty }]
            };

            const btn = document.getElementById('saveIssueBtn');
            UI.setButtonLoading(btn, true, 'Отправка...');

            try {
                const res = await apiFetch(`${API_BASE_URL}/issues/`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${Auth.getToken()}` },
                    body: JSON.stringify(data)
                });

                if (res.ok) {
                    form.reset();
                    if (dateInput) dateInput.value = new Date().toISOString().split('T')[0];

                    const modal = bootstrap.Modal.getInstance(document.getElementById('addIssueModal'));
                    if (modal) modal.hide();

                    UI.showAlert('issuesAlert', 'Расход успешно оформлен!', 'success');
                    loadIssuesList();
                    loadMaterialsForSelect();
                } else {
                    let errMsg = `Ошибка ${res.status}`;
                    try {
                        const err = await res.json();
                        if (typeof err.detail === 'string') errMsg = err.detail;
                    } catch (e) {}
                    UI.showAlert('modalIssueAlert', errMsg, 'danger');
                }
            } catch (e) {
                if (e.message !== 'unauthorized') {
                    console.error('[issues]', e);
                    UI.showAlert('modalIssueAlert', 'Ошибка сети', 'danger');
                }
            } finally {
                UI.setButtonLoading(btn, false);
            }
        });
    }

    const delBtn = document.getElementById('deleteIssueBtn');
    if (delBtn) {
        delBtn.addEventListener('click', async () => {
            if (!currentIssueId) return;
            const num = document.getElementById('viewIssueNumber').textContent;
            if (!confirm(`Удалить расход ${num}?\n\nМатериалы вернутся на склад в прежнем количестве.`)) return;

            delBtn.disabled = true;
            delBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Удаление...';

            try {
                const res = await apiFetch(`${API_BASE_URL}/issues/${currentIssueId}`, {
                    method: 'DELETE',
                    headers: { 'Authorization': `Bearer ${Auth.getToken()}` }
                });

                if (res.ok) {
                    const modalEl = document.getElementById('viewIssueModal');
                    const modal = bootstrap.Modal.getInstance(modalEl);
                    if (modal) modal.hide();

                    UI.showAlert('issuesAlert', 'Расход удалён', 'success');
                    loadIssuesList();
                    loadMaterialsForSelect();
                } else {
                    let errMsg = `Ошибка ${res.status}`;
                    try {
                        const err = await res.json();
                        if (typeof err.detail === 'string') errMsg = err.detail;
                    } catch (e) {}
                    alert(errMsg);
                }
            } catch (e) {
                if (e.message !== 'unauthorized') console.error('[delete issue]', e);
            } finally {
                delBtn.disabled = false;
                delBtn.innerHTML = '🗑 Удалить расход';
            }
        });
    }
}

// ==========================================
// ОБЩАЯ ИНИЦИАЛИЗАЦИЯ
// ==========================================
document.addEventListener('DOMContentLoaded', () => {
    const logoutBtn = document.getElementById('logoutBtn');
    if (logoutBtn) logoutBtn.addEventListener('click', (e) => { e.preventDefault(); Auth.logout(); });

    const userBadgeEl = document.getElementById('userDisplayName');
    if (userBadgeEl) {
        const u = Auth.getUser();
        userBadgeEl.textContent = (u.role === 'admin') ? 'Администратор' : 'Кладовщик';
    }

    if (document.getElementById('loginForm')) initLoginPage();
    if (document.getElementById('materialsTableBody')) initMaterialsPage();
    if (document.getElementById('addReceiptForm')) initReceiptsPage();
    if (document.getElementById('addIssueForm')) initIssuesPage();
});