from flask import Flask, render_template, request, jsonify
import sqlite3
from datetime import datetime, timedelta
import os

app = Flask(__name__)
DB = 'shifts.db'

# ===== Ваши настройки =====
BASE_RATE = 239.0      # ставка 2, Кухня
NIGHT_MULT = 1.3       # +30% за ночь
HOLIDAY_MULT = 2.0     # ×2 праздник


def init_db():
    """Создаёт таблицу смен, если её нет"""
    conn = sqlite3.connect(DB)
    conn.execute('''
        CREATE TABLE IF NOT EXISTS shifts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            start_time TEXT NOT NULL,
            end_time TEXT NOT NULL,
            is_holiday INTEGER DEFAULT 0,
            comment TEXT DEFAULT '',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()


def split_hours(start_dt, end_dt):
    """
    Возвращает (обычные_часы, ночные_часы).
    Ночь: с 22:00 до 06:00.
    """
    regular = 0.0
    night = 0.0
    cur = start_dt
    while cur < end_dt:
        h = cur.hour
        if h >= 22 or h < 6:
            night += 1 / 60
        else:
            regular += 1 / 60
        cur += timedelta(minutes=1)
    return round(regular, 4), round(night, 4)

def get_break_minutes(total_minutes):
    """
    Возвращает длительность перерыва в минутах
    по правилам ресторана.
    """
    if total_minutes <= 4 * 60 + 15:      # ≤ 4:15
        return 15
    if total_minutes <= 8 * 60 + 30:      # ≤ 8:30
        return 30
    if total_minutes <= 12 * 60 + 45:     # ≤ 12:45
        return 45
    return 60                              # > 12:45


def calc_shift(date_str, start_time, end_time, is_holiday):
    """Считает часы и оплату одной смены (с учётом перерыва)"""
    start_dt = datetime.strptime(f"{date_str} {start_time}", "%Y-%m-%d %H:%M")
    end_dt = datetime.strptime(f"{date_str} {end_time}", "%Y-%m-%d %H:%M")

    # Если уход раньше прихода — смена ночная
    if end_dt <= start_dt:
        end_dt += timedelta(days=1)

    # Общая длительность в минутах
    total_minutes = int((end_dt - start_dt).total_seconds() / 60)

    # Перерыв
    break_min = get_break_minutes(total_minutes)

    # Разбивка на обычные и ночные часы (в минутах)
    reg_min = 0
    night_min = 0
    cur = start_dt
    while cur < end_dt:
        h = cur.hour
        if h >= 22 or h < 6:
            night_min += 1
        else:
            reg_min += 1
        cur += timedelta(minutes=1)

    # Вычитаем перерыв пропорционально
    total_work_min = reg_min + night_min
    if total_work_min > 0:
        reg_break = round(break_min * reg_min / total_work_min)
        night_break = break_min - reg_break
        reg_min -= reg_break
        night_min -= night_break

    # В часы
    regular = round(reg_min / 60, 4)
    night = round(night_min / 60, 4)
    total = round(regular + night, 2)

    # Оплата
    day_rate = BASE_RATE * HOLIDAY_MULT if is_holiday else BASE_RATE
    night_rate = BASE_RATE * NIGHT_MULT
    pay = regular * day_rate + night * night_rate

    return {
        'total_hours': round(total, 2),
        'regular_hours': round(regular, 2),
        'night_hours': round(night, 2),
        'break_minutes': break_min,
        'pay': round(pay, 2),
        'day_rate': round(day_rate, 2),
        'night_rate': round(night_rate, 2),
    }


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/shifts', methods=['GET'])
def get_shifts():
    """Возвращает все смены с расчётами + итоги за текущий месяц"""
    month = request.args.get('month')  # 'YYYY-MM', опционально

    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    if month:
        cur.execute(
            "SELECT * FROM shifts WHERE date LIKE ? ORDER BY id DESC",
            (f"{month}%",)
        )
    else:
        cur.execute("SELECT * FROM shifts ORDER BY id DESC")

    rows = [dict(r) for r in cur.fetchall()]
    conn.close()

    result = []
    total_pay = 0.0
    total_hours = 0.0
    total_regular = 0.0
    total_night = 0.0

    for r in rows:
        calc = calc_shift(r['date'], r['start_time'], r['end_time'], bool(r['is_holiday']))
        item = {**r, **calc}
        result.append(item)

        total_pay += calc['pay']
        total_hours += calc['total_hours']
        total_regular += calc['regular_hours']
        total_night += calc['night_hours']

    # Итог за текущий месяц
    now = datetime.now()
    current_month = now.strftime('%Y-%m')
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM shifts WHERE date LIKE ?", (f"{current_month}%",))
    month_rows = [dict(r) for r in cur.fetchall()]
    conn.close()

    month_pay = 0.0
    month_hours = 0.0
    for r in month_rows:
        c = calc_shift(r['date'], r['start_time'], r['end_time'], bool(r['is_holiday']))
        month_pay += c['pay']
        month_hours += c['total_hours']

    return jsonify({
        'shifts': result,
        'total': {
            'pay': round(total_pay, 2),
            'hours': round(total_hours, 2),
            'regular': round(total_regular, 2),
            'night': round(total_night, 2),
            'count': len(result),
        },
        'month': {
            'pay': round(month_pay, 2),
            'hours': round(month_hours, 2),
            'count': len(month_rows),
        }
    })


@app.route('/api/shifts', methods=['POST'])
def add_shift():
    """Добавляет смену"""
    data = request.get_json()

    date = data.get('date')
    start_time = data.get('start_time')
    end_time = data.get('end_time')
    is_holiday = 1 if data.get('is_holiday') else 0
    comment = data.get('comment', '')

    if not date or not start_time or not end_time:
        return jsonify({'error': 'Заполните все поля'}), 400

    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO shifts (date, start_time, end_time, is_holiday, comment) VALUES (?, ?, ?, ?, ?)",
        (date, start_time, end_time, is_holiday, comment)
    )
    conn.commit()
    shift_id = cur.lastrowid
    conn.close()

    calc = calc_shift(date, start_time, end_time, bool(is_holiday))

    return jsonify({
        'id': shift_id,
        'date': date,
        'start_time': start_time,
        'end_time': end_time,
        'is_holiday': is_holiday,
        'comment': comment,
        **calc
    }), 201


@app.route('/api/shifts/<int:shift_id>', methods=['DELETE'])
def delete_shift(shift_id):
    """Удаляет смену"""
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("DELETE FROM shifts WHERE id = ?", (shift_id,))
    conn.commit()
    affected = cur.rowcount
    conn.close()

    if affected == 0:
        return jsonify({'error': 'Смена не найдена'}), 404
    return jsonify({'ok': True})


@app.route('/api/config')
def get_config():
    """Возвращает текущие ставки"""
    return jsonify({
        'base_rate': BASE_RATE,
        'night_mult': NIGHT_MULT,
        'holiday_mult': HOLIDAY_MULT,
    })


if __name__ == '__main__':
    init_db()
    print("=" * 50)
    print("🚀 Сервер запущен!")
    print("🌐 Откройте в браузере: http://localhost:5000")
    print("📱 На телефоне (в той же Wi-Fi сети): http://<IP-компьютера>:5000")
    print("=" * 50)
    app.run(host='0.0.0.0', port=5000, debug=True)