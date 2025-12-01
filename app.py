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
            # Если это конкретный IP, сканируем только его
            subnet = f"{subnet}/32"
            return subnet, f"Сканируется один IP: {subnet}"
        except ValueError:
            return None, f"Некорректный IP-адрес: {subnet}"
    
    # Проверяем корректность подсети CIDR
    try:
        network = ipaddress.ip_network(subnet, strict=False)
        
        # Ограничиваем размер сканируемой подсети
        if network.num_addresses > 256:
            flash(f"Подсеть слишком большая. Сканируем только первые 256 адресов из {subnet}", "warning")
        
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
        total_devices = 0
        active_devices = 0
        recent_scans = []
        recent_equipment = []
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
            # Импортируем сканер
            try:
                from scanner import NetworkScanner
            except ImportError:
                flash('Модуль сканирования не найден', 'error')
                return redirect(url_for('scan_network'))
            
            # Создаем сканер с ограничением
            scanner = NetworkScanner()
            
            print(f"🔄 Запуск сканирования подсети: {subnet}, VLAN: {vlan_id}")
            
            # Ограничиваем время сканирования
            import threading
            from queue import Queue
            
            result_queue = Queue()
            
            def run_scan():
                try:
                    scan_results = scanner.scan_subnet(subnet, vlan_id, max_threads=10, timeout=1)
                    result_queue.put(('success', scan_results))
                except Exception as e:
                    result_queue.put(('error', str(e)))
            
            # Запускаем в отдельном потоке с таймаутом
            scan_thread = threading.Thread(target=run_scan)
            scan_thread.daemon = True
            scan_thread.start()
            
            # Ждем максимум 30 секунд
            scan_thread.join(timeout=30)
            
            if scan_thread.is_alive():
                flash('Сканирование прервано по таймауту (30 секунд)', 'warning')
                return redirect(url_for('scan_network'))
            
            # Получаем результаты
            if result_queue.empty():
                flash('Сканирование не вернуло результатов', 'error')
                return redirect(url_for('scan_network'))
            
            status, result = result_queue.get()
            
            if status == 'error':
                flash(f'Ошибка сканирования: {result}', 'error')
                return redirect(url_for('scan_network'))
            
            scan_results = result
            
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
            
            if len(scan_results) > 0:
                flash(f'✅ Найдено {len(scan_results)} устройств в подсети {subnet}', 'success')
            else:
                flash(f'ℹ️ Устройства в подсети {subnet} не найдены', 'info')
            
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

@app.route('/scan/quick', methods=['GET', 'POST'])
def quick_scan():
    """Быстрое сканирование (только несколько адресов)"""
    if request.method == 'POST':
        # Определяем локальную сеть автоматически
        import netifaces
        
        try:
            # Получаем IP текущего интерфейса
            gateways = netifaces.gateways()
            default_gateway = gateways['default'][netifaces.AF_INET]
            current_ip = socket.gethostbyname(socket.gethostname())
            
            # Создаем подсеть /24 на основе текущего IP
            parts = current_ip.split('.')
            subnet = f"{parts[0]}.{parts[1]}.{parts[2]}.0/24"
            
            flash(f'Автоматически определена подсеть: {subnet}', 'info')
            
            # Перенаправляем на обычное сканирование
            session['preset_subnet'] = subnet
            return redirect(url_for('scan_network'))
            
        except Exception as e:
            flash(f'Не удалось определить локальную сеть: {str(e)}', 'error')
            return redirect(url_for('scan_network'))
    
    return render_template('quick_scan.html')

@app.route('/reports')
def reports():
    """Страница с отчетами"""
    try:
        dept_stats = db.session.query(
            Equipment.department,
            db.func.count(Equipment.id)
        ).group_by(Equipment.department).all()
        
        os_stats = db.session.query(
            Equipment.os_name,
            db.func.count(Equipment.id)
        ).group_by(Equipment.os_name).all()
        
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

@app.route('/api/scan/status')
def scan_status():
    """API для проверки статуса сканирования"""
    scan_data = session.get('scan_results')
    if not scan_data:
        return jsonify({'status': 'no_scan'})
    
    return jsonify({
        'status': 'complete',
        'subnet': scan_data['subnet'],
        'devices_found': len(scan_data['results']),
        'timestamp': scan_data['timestamp']
    })

@app.route('/system/health')
def system_health():
    """Проверка здоровья системы"""
    try:
        db_status = Config.check_database_connection()
        
        stats = {
            'database': 'healthy' if db_status else 'unhealthy',
            'equipment_count': Equipment.query.count(),
            'active_equipment': Equipment.query.filter_by(is_active=True).count(),
            'scans_count': ScanHistory.query.count(),
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
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_server_error(e):
    return render_template('500.html'), 500

if __name__ == '__main__':
    if not wait_for_database():
        print("⚠️  Предупреждение: База данных недоступна, но приложение запускается")
    
    print("🚀 Запуск IT Inventory System...")
    print(f"📊 База данных: {Config.DB_HOST}:{Config.DB_PORT}/{Config.DB_NAME}")
    print(f"🌐 Приложение доступно по адресу: http://0.0.0.0:5000")
    
    app.run(host='0.0.0.0', port=5000, debug=True)