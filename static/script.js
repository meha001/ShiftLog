// ===== Загрузка данных =====
async function loadShifts() {
    const list = document.getElementById('shifts-list');
    try {
        const res = await fetch('/api/shifts');
        if (!res.ok) throw new Error('HTTP ' + res.status);
        const data = await res.json();
        console.log('Данные с сервера:', data); // ← для отладки
        renderShifts(data.shifts || []);
        renderTotals(data);
    } catch (e) {
        console.error('Ошибка загрузки:', e);
        list.innerHTML = '<div class="empty">Ошибка загрузки данных: ' + e.message + '</div>';
    }
}

// ===== Отрисовка итогов =====
function renderTotals(data) {
    const fmt = (n) => (n || 0).toLocaleString('ru-RU', { maximumFractionDigits: 0 }) + ' ₽';
    const month = data.month || { pay: 0, hours: 0, count: 0 };
    const total = data.total || { pay: 0, hours: 0, count: 0 };

    document.getElementById('month-pay').textContent = fmt(month.pay);
    document.getElementById('month-hours').textContent =
        `${month.hours} ч • ${month.count} смен`;

    document.getElementById('total-pay').textContent = fmt(total.pay);
    document.getElementById('total-hours').textContent =
        `${total.hours} ч • ${total.count} смен`;
}

// ===== Отрисовка списка смен =====
function renderTotals(data) {
    const fmtMoney = (n) => (n || 0).toLocaleString('ru-RU', { maximumFractionDigits: 0 }) + ' ₽';
    const month = data.month || { pay: 0, hours: 0, count: 0 };
    const total = data.total || { pay: 0, hours: 0, count: 0 };

    document.getElementById('month-pay').textContent = fmtMoney(month.pay);
    document.getElementById('month-hours').textContent =
        `${month.hours} ч · ${month.count} смен`;

    document.getElementById('total-pay').textContent = fmtMoney(total.pay);
    document.getElementById('total-hours').textContent =
        `${total.hours} ч · ${total.count} смен`;
}

function renderShifts(shifts) {
    const list = document.getElementById('shifts-list');

    if (!shifts || shifts.length === 0) {
        list.innerHTML = '<div class="empty">Нет данных. Добавьте первую смену.</div>';
        return;
    }

    list.innerHTML = shifts.map(s => {
        const date = formatDate(s.date);
        const hours = (s.total_hours || 0).toFixed(1);
        const holidayClass = s.is_holiday ? ' holiday' : '';
        const holiday = s.is_holiday ? '<span class="holiday-badge">×2</span>' : '';
        const comment = s.comment
            ? `<div class="shift-detail">// ${escapeHtml(s.comment)}</div>`
            : '';
        const breakInfo = s.break_minutes
            ? `<div class="shift-detail">перерыв ${s.break_minutes} мин</div>`
            : '';

        return `
            <div class="shift-item${holidayClass}">
                <div class="shift-hours">${hours}ч</div>
                <div class="shift-info">
                    <div class="shift-date">${date}${holiday}</div>
                    <div class="shift-time">${s.start_time} → ${s.end_time}</div>
                    <div class="shift-detail">${s.regular_hours} об + ${s.night_hours} ноч</div>
                    ${breakInfo}
                    ${comment}
                </div>
                <div class="shift-pay">${(s.pay || 0).toFixed(0)} ₽</div>
                <button class="shift-delete" onclick="deleteShift(${s.id})" title="Удалить">×</button>
            </div>
        `;
    }).join('');
}

function toggleHoliday() {
    const cb = document.getElementById('input-holiday');
    const label = document.getElementById('holiday-label');
    label.classList.toggle('checked', cb.checked);
}

// ===== Утилиты =====
function formatDate(dateStr) {
    if (!dateStr) return '';
    const [y, m, d] = dateStr.split('-');
    return `${d}.${m}.${y}`;
}

function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

// ===== Модальное окно =====
function openModal() {
    const now = new Date();
    const iso = now.toISOString().slice(0, 10);
    document.getElementById('input-date').value = iso;
    document.getElementById('input-start').value = '18:00';
    document.getElementById('input-end').value = '03:00';
    document.getElementById('input-holiday').checked = false;
    document.getElementById('input-comment').value = '';
    document.getElementById('modal').classList.add('active');
    toggleHoliday();
}

function closeModal() {
    document.getElementById('modal').classList.remove('active');
}

function closeModalOutside(e) {
    if (e.target.id === 'modal') closeModal();
}

// ===== Сохранение смены =====
async function saveShift() {
    const date = document.getElementById('input-date').value;
    const start_time = document.getElementById('input-start').value;
    const end_time = document.getElementById('input-end').value;
    const is_holiday = document.getElementById('input-holiday').checked;
    const comment = document.getElementById('input-comment').value.trim();

    if (!date || !start_time || !end_time) {
        alert('Заполните дату, время прихода и ухода');
        return;
    }

    try {
        const res = await fetch('/api/shifts', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ date, start_time, end_time, is_holiday, comment })
        });

        if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            alert('Ошибка: ' + (err.error || 'неизвестная'));
            return;
        }

        const shift = await res.json();
        closeModal();
        await loadShifts();

        setTimeout(() => {
            alert(
                `✅ Смена добавлена!\n\n` +
                `Всего часов: ${shift.total_hours}\n` +
                `Обычных: ${shift.regular_hours}\n` +
                `Ночных: ${shift.night_hours}\n` +
                (shift.break_minutes ? `Перерыв: ${shift.break_minutes} мин\n` : '') +
                `\nЗа смену: ${shift.pay.toFixed(2)} р`
            );
        }, 100);

    } catch (e) {
        console.error(e);
        alert('Ошибка соединения с сервером: ' + e.message);
    }
}

// ===== Удаление смены =====
async function deleteShift(id) {
    if (!confirm('Удалить эту смену?')) return;

    try {
        const res = await fetch(`/api/shifts/${id}`, { method: 'DELETE' });
        if (res.ok) {
            await loadShifts();
        } else {
            alert('Не удалось удалить смену');
        }
    } catch (e) {
        console.error(e);
        alert('Ошибка соединения');
    }
}

// ===== Инициализация =====
document.addEventListener('DOMContentLoaded', loadShifts);

function toggleHoliday() {
    const cb = document.getElementById('input-holiday');
    const label = document.getElementById('holiday-label');
    if (cb.checked) {
        label.classList.add('checked');
    } else {
        label.classList.remove('checked');
    }
}
