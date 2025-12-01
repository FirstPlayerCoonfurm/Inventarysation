from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, session
from models import db, Equipment, ScanHistory
from config import Config
from datetime import datetime
import socket
import time
import sys
import ipaddress

app = Flask(__name__)
app.config.from_object(Config)
app.secret_key = Config.SECRET_KEY

# Инициализация базы данных
db.init_app(app)

# Импортируем NetworkScanner локально, чтобы избежать циклических импортов
def import_scanner():
    from scanner import NetworkScanner
    return NetworkScanner

def wait_for_database():
    """Ожидает доступность базы данных"""
    print("🔍 Проверка подключения к базе данных...")
    
    for i in range(30):
        if Config.check_database_connection():
            print("✅ База данных доступна")
            return True
        print(f"⏳ Ожидание базы данных... ({i+1}/30)")
        time.sleep(2)
    
    print("❌ Не удалось подключиться к базе данных")
    return False

def validate_subnet_input(subnet):
    """Проверяет и форматирует введенную подсеть"""
    if not subnet:
        return None, "Поле 'Подсеть' не может быть пустым"
    
    subnet = subnet.strip()
    
    # Если введен просто IP, добавляем /24 по умолчанию
    if '/' not in subnet:
        # Проверяем, является ли это валидным IP
        try:
            ipaddress.ip_address(subnet)
            subnet = f"{subnet}/24"
            return subnet, f"Автоматически добавлена маска /24. Сканируется: {subnet}"
        except ValueError:
            return None, f"Некорректный IP-адрес: {subnet}"
    
    # Проверяем корректность подсети CIDR
    try:
        network = ipaddress.ip_network(subnet, strict=False)
        return subnet, None
    except ValueError as e:
        return None, f"Некорректная подсеть: {e}"

@app.route('/')
def index():
    """Главная страница с общей статистикой"""
    try:
        total_devices = Equipment.query.count()
        active_devices = Equipment.query.filter_by(is_active=True).count()
        recent_scans = ScanHistory.query.order_by(ScanHistory.scan_date.desc()).limit(5).all()
        recent_equipment = Equipment.query.order_by(Equipment.last_seen.desc()).limit(5).all()
        
    except Exception as e:
        print(f"Ошибка базы данных: {e}")
        # Если есть ошибка, используем тестовые данные
        total_devices = 0
        active_devices = 0
        recent_scans = []
        recent_equipment = []
        
        # Показываем сообщение об ошибке
        flash(f'Ошибка подключения к базе данных: {e}', 'error')

    return render_template('index.html',
                         total_devices=total_devices,
                         active_devices=active_devices,
                         recent_scans=recent_scans,
                         recent_equipment=recent_equipment)

@app.route('/equipment')
def equipment_list():
    """Список всего оборудования"""
    try:
        search = request.args.get('search', '')
        
        query = Equipment.query
        
        if search:
            query = query.filter(
                (Equipment.hostname.contains(search)) |
                (Equipment.ip_address.contains(search)) |
                (Equipment.inventory_number.contains(search))
            )
        
        # Убираем пагинацию - получаем все результаты
        equipment = query.order_by(Equipment.last_seen.desc()).all()
        
    except Exception as e:
        flash(f'Ошибка загрузки оборудования: {e}', 'error')
        equipment = []
        search = ''

    return render_template('equipment_list.html', 
                         equipment=equipment, 
                         search=search)

@app.route('/equipment/<int:equipment_id>')
def equipment_detail(equipment_id):
    """Детальная информация об оборудовании"""
    try:
        equipment = Equipment.query.get_or_404(equipment_id)
        return render_template('equipment_detail.html', equipment=equipment)
    except Exception as e:
        flash(f'Ошибка загрузки оборудования: {e}', 'error')
        return redirect(url_for('equipment_list'))

@app.route('/scan', methods=['GET', 'POST'])
def scan_network():
    """Страница сканирования сети"""
    if request.method == 'POST':
        subnet_input = request.form.get('subnet', '').strip()
        vlan_id_input = request.form.get('vlan_id', '').strip()
        
        # Валидация подсети
        subnet, subnet_message = validate_subnet_input(subnet_input)
        if subnet is None:
            flash(subnet_message, 'error')
            return redirect(url_for('scan_network'))
        
        if subnet_message:
            flash(subnet_message, 'info')
        
        # Валидация VLAN ID
        vlan_id = None
        if vlan_id_input:
            try:
                vlan_id = int(vlan_id_input)
                if not (1 <= vlan_id <= 4094):
                    flash('Ошибка: VLAN ID должен быть в диапазоне 1-4094', 'error')
                    return redirect(url_for('scan_network'))
            except ValueError:
                flash('Ошибка: VLAN ID должен быть числом', 'error')
                return redirect(url_for('scan_network'))
        
        try:
            # Запускаем реальное сканирование
            NetworkScanner = import_scanner()
            scanner = NetworkScanner()
            
            print(f"🔄 Запуск сканирования подсети: {subnet}, VLAN: {vlan_id}")
            scan_results = scanner.scan_subnet(subnet, vlan_id, max_threads=50)
            
            # Сохраняем запись о сканировании
            scan_record = ScanHistory(
                subnet_scanned=subnet,
                devices_found=len(scan_results),
                scan_type='manual',
                initiated_by='Администратор',
                vlan_id=vlan_id
            )
            db.session.add(scan_record)
            db.session.commit()
            
            # Сохраняем результаты в сессии
            session['scan_results'] = {
                'subnet': subnet,
                'vlan_id': vlan_id,
                'results': scan_results,
                'timestamp': datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'),
                'scan_id': scan_record.id
            }
            
            flash(f'✅ Найдено {len(scan_results)} устройств в подсети {subnet}', 'success')
            return redirect(url_for('scan_results'))
            
        except Exception as e:
            flash(f'❌ Ошибка сканирования: {str(e)}', 'error')
            return redirect(url_for('scan_network'))
    
    return render_template('scan.html')

@app.route('/scan/results')
def scan_results():
    """Страница результатов сканирования"""
    scan_data = session.get('scan_results')
    if not scan_data:
        flash('Нет результатов сканирования. Запустите сканирование сначала.', 'warning')
        return redirect(url_for('scan_network'))
    
    # Получаем дополнительную информацию из базы данных
    scan_record = None
    if 'scan_id' in scan_data:
        scan_record = ScanHistory.query.get(scan_data['scan_id'])
    
    return render_template('scan_results.html',
                         subnet=scan_data['subnet'],
                         vlan_id=scan_data['vlan_id'],
                         results=scan_data['results'],
                         timestamp=scan_data['timestamp'],
                         scan_record=scan_record)

@app.route('/scan/clear')
def clear_scan_results():
    """Очистка результатов сканирования"""
    session.pop('scan_results', None)
    flash('Результаты сканирования очищены', 'info')
    return redirect(url_for('scan_network'))

@app.route('/reports')
def reports():
    """Страница с отчетами"""
    try:
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
        
        # Статистика по VLAN
        vlan_stats = db.session.query(
            Equipment.vlan_id,
            db.func.count(Equipment.id)
        ).filter(Equipment.vlan_id.isnot(None)).group_by(Equipment.vlan_id).all()
        
    except Exception as e:
        flash(f'Ошибка загрузки отчетов: {e}', 'error')
        dept_stats = []
        os_stats = []
        vlan_stats = []
    
    return render_template('reports.html',
                         dept_stats=dept_stats,
                         os_stats=os_stats,
                         vlan_stats=vlan_stats)

@app.route('/api/equipment')
def api_equipment():
    """API endpoint для данных оборудования"""
    try:
        equipment = Equipment.query.all()
        return jsonify([{
            'id': eq.id,
            'ip_address': eq.ip_address,
            'hostname': eq.hostname,
            'mac_address': eq.mac_address,
            'os_name': eq.os_name,
            'vlan_id': eq.vlan_id,
            'last_seen': eq.last_seen.isoformat() if eq.last_seen else None,
            'is_active': eq.is_active
        } for eq in equipment])
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/scan/quick', methods=['POST'])
def api_quick_scan():
    """Быстрое сканирование через API"""
    try:
        data = request.get_json()
        subnet = data.get('subnet', '').strip()
        vlan_id = data.get('vlan_id')
        
        if not subnet:
            return jsonify({'error': 'Не указана подсеть'}), 400
        
        # Валидация подсети
        subnet, error = validate_subnet_input(subnet)
        if error:
            return jsonify({'error': error}), 400
        
        # Конвертируем VLAN ID
        vlan_id_int = None
        if vlan_id:
            try:
                vlan_id_int = int(vlan_id)
                if not (1 <= vlan_id_int <= 4094):
                    return jsonify({'error': 'VLAN ID должен быть в диапазоне 1-4094'}), 400
            except ValueError:
                return jsonify({'error': 'VLAN ID должен быть числом'}), 400
        
        # Запускаем сканирование
        NetworkScanner = import_scanner()
        scanner = NetworkScanner()
        results = scanner.scan_subnet(subnet, vlan_id_int, max_threads=20)
        
        return jsonify({
            'success': True,
            'subnet': subnet,
            'vlan_id': vlan_id_int,
            'devices_found': len(results),
            'devices': results[:10]  # Возвращаем только первые 10 устройств
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/equipment/<int:equipment_id>', methods=['PUT'])
def api_update_equipment(equipment_id):
    """Обновление информации об оборудовании через API"""
    try:
        equipment = Equipment.query.get_or_404(equipment_id)
        data = request.get_json()
        
        # Обновляем разрешенные поля
        updatable_fields = ['inventory_number', 'location', 'department', 
                           'responsible_person', 'notes']
        
        for field in updatable_fields:
            if field in data:
                setattr(equipment, field, data[field])
        
        equipment.last_seen = datetime.utcnow()
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Оборудование обновлено',
            'equipment': {
                'id': equipment.id,
                'ip_address': equipment.ip_address,
                'hostname': equipment.hostname
            }
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/check-db')
def check_database():
    """Проверка подключения к базе данных"""
    try:
        device_count = Equipment.query.count()
        scan_count = ScanHistory.query.count()
        return f'''
        <h1>✅ Подключение к базе данных успешно!</h1>
        <div class="alert alert-success">
            <p><strong>Устройств в базе:</strong> {device_count}</p>
            <p><strong>Записей сканирования:</strong> {scan_count}</p>
            <p><strong>Последнее сканирование:</strong> {ScanHistory.query.order_by(ScanHistory.scan_date.desc()).first().scan_date if scan_count > 0 else 'Нет данных'}</p>
        </div>
        <a href="/" class="btn btn-primary">На главную</a>
        '''
    except Exception as e:
        return f'''
        <h1>❌ Ошибка подключения к базе данных!</h1>
        <div class="alert alert-danger">
            <p><strong>Ошибка:</strong> {e}</p>
        </div>
        <a href="/" class="btn btn-primary">На главную</a>
        '''

@app.route('/system/health')
def system_health():
    """Проверка здоровья системы"""
    try:
        # Проверяем подключение к БД
        db_status = Config.check_database_connection()
        
        # Получаем статистику
        stats = {
            'database': 'healthy' if db_status else 'unhealthy',
            'equipment_count': Equipment.query.count(),
            'active_equipment': Equipment.query.filter_by(is_active=True).count(),
            'scans_count': ScanHistory.query.count(),
            'uptime': time.time() - app_start_time if 'app_start_time' in globals() else 0
        }
        
        return jsonify({
            'status': 'healthy' if db_status else 'degraded',
            'timestamp': datetime.utcnow().isoformat(),
            'components': stats
        })
        
    except Exception as e:
        return jsonify({
            'status': 'unhealthy',
            'error': str(e),
            'timestamp': datetime.utcnow().isoformat()
        }), 500

@app.errorhandler(404)
def page_not_found(e):
    """Обработчик ошибки 404"""
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_server_error(e):
    """Обработчик ошибки 500"""
    return render_template('500.html'), 500

# Инициализация при запуске
if __name__ == '__main__':
    # Сохраняем время старта для health check
    global app_start_time
    app_start_time = time.time()
    
    # Ожидаем доступность базы данных перед запуском
    if not wait_for_database():
        print("⚠️  Предупреждение: База данных недоступна, но приложение запускается")
    
    print("🚀 Запуск IT Inventory System...")
    print(f"📊 База данных: {Config.DB_HOST}:{Config.DB_PORT}/{Config.DB_NAME}")
    print(f"🌐 Приложение доступно по адресу: http://0.0.0.0:5000")
    
    app.run(host='0.0.0.0', port=5000, debug=True)