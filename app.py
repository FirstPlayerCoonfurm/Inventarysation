from flask import Flask, render_template, request, jsonify, redirect, url_for
from models import db, Equipment, ScanHistory
from config import Config
from scanner import NetworkScanner
from datetime import datetime
import json
import socket
import time
import sys

app = Flask(__name__)
app.config.from_object(Config)

# Инициализация базы данных
db.init_app(app)

@app.route('/')
def index():
    """Главная страница с общей статистикой"""
    total_devices = Equipment.query.count()
    active_devices = Equipment.query.filter_by(is_active=True).count()
    recent_scans = ScanHistory.query.order_by(ScanHistory.scan_date.desc()).limit(5).all()
    
    return render_template('index.html', 
                         total_devices=total_devices,
                         active_devices=active_devices,
                         recent_scans=recent_scans)

@app.route('/equipment')
def equipment_list():
    """Список всего оборудования"""
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '')
    
    query = Equipment.query
    
    if search:
        query = query.filter(
            (Equipment.hostname.contains(search)) |
            (Equipment.ip_address.contains(search)) |
            (Equipment.inventory_number.contains(search))
        )
    
    equipment = query.order_by(Equipment.last_seen.desc()).paginate(
        page=page, per_page=50, error_out=False
    )
    
    return render_template('equipment_list.html', 
                         equipment=equipment,
                         search=search)

@app.route('/api/equipment')
def api_equipment():
    """API endpoint для данных оборудования (для AJAX)"""
    equipment = Equipment.query.all()
    return jsonify([eq.to_dict() for eq in equipment])

@app.route('/scan', methods=['GET', 'POST'])
def scan_network():
    """Страница сканирования сети"""
    if request.method == 'POST':
        subnet = request.form.get('subnet')
        vlan_id = request.form.get('vlan_id', type=int)
        
        scanner = NetworkScanner()
        results = scanner.scan_subnet(subnet, vlan_id)
        
        # Сохраняем результаты сканирования
        scan_record = ScanHistory(
            subnet_scanned=subnet,
            devices_found=len(results),
            scan_type='manual',
            initiated_by='Admin'  # В реальном приложении - текущий пользователь
        )
        db.session.add(scan_record)
        db.session.commit()
        
        return render_template('scan_results.html', 
                             results=results, 
                             subnet=subnet,
                             vlan_id=vlan_id)
    
    return render_template('scan.html')

@app.route('/api/scan', methods=['POST'])
def api_scan_network():
    """API для сканирования сети (AJAX)"""
    data = request.get_json()
    subnet = data.get('subnet')
    vlan_id = data.get('vlan_id')
    
    scanner = NetworkScanner()
    results = scanner.scan_subnet(subnet, vlan_id)
    
    return jsonify(results)

@app.route('/equipment/<int:equipment_id>')
def equipment_detail(equipment_id):
    """Детальная информация об оборудовании"""
    equipment = Equipment.query.get_or_404(equipment_id)
    return render_template('equipment_detail.html', equipment=equipment)

@app.route('/api/equipment/<int:equipment_id>', methods=['PUT'])
def api_update_equipment(equipment_id):
    """API для обновления информации об оборудовании"""
    equipment = Equipment.query.get_or_404(equipment_id)
    data = request.get_json()
    
    # Обновляем поля
    for field in ['inventory_number', 'location', 'department', 'responsible_person']:
        if field in data:
            setattr(equipment, field, data[field])
    
    equipment.last_seen = datetime.utcnow()
    db.session.commit()
    
    return jsonify(equipment.to_dict())

@app.route('/reports')
def reports():
    """Страница с отчетами"""
    # Статистика по отделам
    dept_stats = db.session.query(
        Equipment.department,
        db.func.count(Equipment.id)
    ).group_by(Equipment.department).all()
    
    # Статистика по ОС
    os_stats = db.session.query(
        Equipment.os_name,
        db.func.count(Equipment.id)
    ).group_by(Equipment.os_name).all()
    
    return render_template('reports.html',
                         dept_stats=dept_stats,
                         os_stats=os_stats)

def init_db():
    """Инициализация базы данных"""
    with app.app_context():
        db.create_all()

def wait_for_database():
    """Ожидает доступность базы данных с проверкой DNS"""
    print("🔍 Проверка подключения к базе данных...")

    # Сначала проверяем разрешение имени хоста
    print("🔍 Проверка разрешения имени 'db'...")
    for i in range(30):
        try:
            socket.gethostbyname('db')
            print("✅ Имя 'db' успешно разрешено")
            break
        except socket.gaierror:
            print(f"⏳ Ожидание разрешения имени 'db'... ({i+1}/30)")
            time.sleep(1)
    else:
        print("❌ Не удалось разрешить имя 'db'")
        return False

    # Затем проверяем подключение к базе данных
    print("🔍 Проверка подключения к PostgreSQL...")
    for i in range(30):
        if Config.check_database_connection():
            print("✅ База данных доступна")
            return True
        print(f"⏳ Ожидание базы данных... ({i+1}/30)")
        time.sleep(1)

    print("❌ Не удалось подключиться к базе данных")
    return False

if __name__ == '__main__':
    # Ожидаем доступность базы данных перед запуском
    if not wait_for_database():
        sys.exit(1)

    print("🚀 Запуск IT Inventory System...")
    app.run(debug=True, host='0.0.0.0')
