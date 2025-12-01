from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, session
from models import db, Equipment, ScanHistory
from config import Config
from datetime import datetime
import socket
import time
import sys
import ipaddress
import re

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
        try:
            ipaddress.ip_address(subnet)
            subnet = f"{subnet}/32"
            return subnet, f"Сканируется один IP: {subnet}"
        except ValueError:
            return None, f"Некорректный IP-адрес: {subnet}"
    
    try:
        network = ipaddress.ip_network(subnet, strict=False)
        
        # УБИРАЕМ ограничение на размер подсети, только предупреждение
        if network.num_addresses > 1000:
            return subnet, f"Большая подсеть: {network.num_addresses} адресов. Сканирование может занять время."
        
        return subnet, None
    except ValueError as e:
        return None, f"Некорректная подсеть: {e}"

def validate_mac_address(mac):
    """Валидация MAC-адреса"""
    if not mac:
        return True, None
    
    mac_pattern = re.compile(r'^([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})$')
    if mac_pattern.match(mac):
        mac = mac.upper().replace('-', ':')
        return True, mac
    return False, "Некорректный формат MAC-адреса. Используйте формат: 00:11:22:33:44:55 или 00-11-22-33-44-55"

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
    """Список всего оборудования с пагинацией"""
    try:
        search = request.args.get('search', '')
        page = request.args.get('page', 1, type=int)
        per_page = 20
        
        query = Equipment.query
        
        if search:
            query = query.filter(
                (Equipment.hostname.contains(search)) |
                (Equipment.ip_address.contains(search)) |
                (Equipment.inventory_number.contains(search)) |
                (Equipment.mac_address.contains(search))
            )
        
        equipment_pagination = query.order_by(Equipment.last_seen.desc()).paginate(
            page=page, per_page=per_page, error_out=False
        )
        
        equipment = equipment_pagination.items
        
    except Exception as e:
        flash(f'Ошибка загрузки оборудования: {e}', 'error')
        equipment_pagination = None
        equipment = []
        search = ''

    return render_template('equipment_list.html', 
                         equipment=equipment, 
                         pagination=equipment_pagination,
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

@app.route('/equipment/<int:equipment_id>/edit', methods=['GET', 'POST'])
def equipment_edit(equipment_id):
    """Редактирование оборудования"""
    equipment = Equipment.query.get_or_404(equipment_id)
    
    if request.method == 'POST':
        try:
            equipment.hostname = request.form.get('hostname', '').strip() or None
            equipment.department = request.form.get('department', '').strip() or None
            equipment.inventory_number = request.form.get('inventory_number', '').strip() or None
            equipment.location = request.form.get('location', '').strip() or None
            equipment.responsible_person = request.form.get('responsible_person', '').strip() or None
            equipment.is_active = 'is_active' in request.form
            
            # Валидация VLAN
            vlan_id = request.form.get('vlan_id', '').strip()
            if vlan_id:
                try:
                    vlan_id = int(vlan_id)
                    if 1 <= vlan_id <= 4094:
                        equipment.vlan_id = vlan_id
                    else:
                        flash('VLAN ID должен быть в диапазоне 1-4094', 'error')
                        return redirect(url_for('equipment_edit', equipment_id=equipment_id))
                except ValueError:
                    flash('VLAN ID должен быть числом', 'error')
                    return redirect(url_for('equipment_edit', equipment_id=equipment_id))
            else:
                equipment.vlan_id = None
            
            # Валидация MAC-адреса
            mac_address = request.form.get('mac_address', '').strip()
            if mac_address:
                is_valid, error_msg = validate_mac_address(mac_address)
                if is_valid:
                    equipment.mac_address = mac_address.upper().replace('-', ':')
                else:
                    flash(error_msg, 'error')
                    return redirect(url_for('equipment_edit', equipment_id=equipment_id))
            else:
                equipment.mac_address = None
            
            equipment.last_seen = datetime.utcnow()
            
            db.session.commit()
            flash('✅ Данные оборудования успешно обновлены', 'success')
            return redirect(url_for('equipment_detail', equipment_id=equipment_id))
            
        except Exception as e:
            db.session.rollback()
            flash(f'❌ Ошибка при обновлении оборудования: {str(e)}', 'error')
            return redirect(url_for('equipment_edit', equipment_id=equipment_id))
    
    return render_template('equipment_edit.html', equipment=equipment)

@app.route('/equipment/<int:equipment_id>/delete', methods=['POST'])
def equipment_delete(equipment_id):
    """Удаление оборудования (мягкое удаление)"""
    try:
        equipment = Equipment.query.get_or_404(equipment_id)
        
        equipment.is_active = False
        equipment.last_seen = datetime.utcnow()
        
        db.session.commit()
        flash('✅ Оборудование помечено как неактивное', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'❌ Ошибка при удалении оборудования: {str(e)}', 'error')
    
    return redirect(url_for('equipment_list'))

@app.route('/equipment/add', methods=['GET', 'POST'])
def equipment_add():
    """Добавление нового оборудования вручную"""
    if request.method == 'POST':
        try:
            ip_address = request.form.get('ip_address', '').strip()
            if not ip_address:
                flash('IP-адрес обязателен для заполнения', 'error')
                return redirect(url_for('equipment_add'))
            
            try:
                ipaddress.ip_address(ip_address)
            except ValueError:
                flash('Некорректный IP-адрес', 'error')
                return redirect(url_for('equipment_add'))
            
            existing = Equipment.query.filter_by(ip_address=ip_address).first()
            if existing:
                flash(f'Оборудование с IP-адресом {ip_address} уже существует', 'error')
                return redirect(url_for('equipment_add'))
            
            mac_address = request.form.get('mac_address', '').strip()
            if mac_address:
                is_valid, error_msg = validate_mac_address(mac_address)
                if not is_valid:
                    flash(error_msg, 'error')
                    return redirect(url_for('equipment_add'))
                mac_address = mac_address.upper().replace('-', ':')
            
            new_equipment = Equipment(
                ip_address=ip_address,
                hostname=request.form.get('hostname', '').strip() or None,
                mac_address=mac_address or None,
                department=request.form.get('department', '').strip() or None,
                inventory_number=request.form.get('inventory_number', '').strip() or None,
                location=request.form.get('location', '').strip() or None,
                responsible_person=request.form.get('responsible_person', '').strip() or None,
                is_active='is_active' in request.form,
                first_discovered=datetime.utcnow(),
                last_seen=datetime.utcnow()
            )
            
            vlan_id = request.form.get('vlan_id', '').strip()
            if vlan_id:
                try:
                    vlan_id = int(vlan_id)
                    if 1 <= vlan_id <= 4094:
                        new_equipment.vlan_id = vlan_id
                    else:
                        flash('VLAN ID должен быть в диапазоне 1-4094', 'error')
                        return redirect(url_for('equipment_add'))
                except ValueError:
                    flash('VLAN ID должен быть числом', 'error')
                    return redirect(url_for('equipment_add'))
            
            db.session.add(new_equipment)
            db.session.commit()
            
            flash('✅ Оборудование успешно добавлено', 'success')
            return redirect(url_for('equipment_detail', equipment_id=new_equipment.id))
            
        except Exception as e:
            db.session.rollback()
            flash(f'❌ Ошибка при добавлении оборудования: {str(e)}', 'error')
            return redirect(url_for('equipment_add'))
    
    return render_template('equipment_add.html')

@app.route('/scan', methods=['GET', 'POST'])
def scan_network():
    """Страница сканирования сети"""
    # Получаем историю сканирований для отображения
    try:
        scan_history = ScanHistory.query.order_by(ScanHistory.scan_date.desc()).limit(10).all()
    except Exception as e:
        scan_history = []
        print(f"⚠️  Не удалось загрузить историю сканирований: {e}")
    
    if request.method == 'POST':
        subnet_input = request.form.get('subnet', '').strip()
        vlan_id_input = request.form.get('vlan_id', '').strip()
        max_threads = request.form.get('max_threads', 50, type=int)
        timeout = request.form.get('timeout', 2, type=int)
        
        # Валидация параметров
        if max_threads < 1 or max_threads > 100:
            max_threads = 50
        if timeout < 1 or timeout > 10:
            timeout = 2
        
        # Валидация подсети
        subnet, subnet_message = validate_subnet_input(subnet_input)
        if subnet is None:
            flash(subnet_message, 'error')
            return render_template('scan.html', scan_history=scan_history)
        
        if subnet_message:
            flash(subnet_message, 'info')
        
        # Валидация VLAN ID
        vlan_id = None
        if vlan_id_input:
            try:
                vlan_id = int(vlan_id_input)
                if not (1 <= vlan_id <= 4094):
                    flash('Ошибка: VLAN ID должен быть в диапазоне 1-4094', 'error')
                    return render_template('scan.html', scan_history=scan_history)
            except ValueError:
                flash('Ошибка: VLAN ID должен быть числом', 'error')
                return render_template('scan.html', scan_history=scan_history)
        
        try:
            from scanner import NetworkScanner
        except ImportError as e:
            flash(f'Модуль сканирования не найден: {e}', 'error')
            return render_template('scan.html', scan_history=scan_history)
        
        scanner = NetworkScanner()
        
        print(f"🔄 Запуск сканирования подсети: {subnet}, VLAN: {vlan_id}")
        print(f"⚙️  Параметры: потоки={max_threads}, таймаут={timeout}с")
        
        # Рассчитываем ожидаемое время
        try:
            network = ipaddress.ip_network(subnet, strict=False)
            num_addresses = network.num_addresses
            estimated_time = max(30, (num_addresses / 100) * timeout)
            
            if num_addresses > 1000:
                flash(f'⚠️  Большая подсеть: {num_addresses} адресов. Сканирование может занять до {estimated_time:.0f} секунд', 'warning')
            
            print(f"⏱️  Ожидаемое время: {estimated_time:.0f} секунд для {num_addresses} адресов")
        except:
            estimated_time = 120
        
        import threading
        from queue import Queue
        
        result_queue = Queue()
        
        def run_scan():
            try:
                scan_results = scanner.scan_subnet(subnet, vlan_id, max_threads=max_threads, timeout=timeout)
                result_queue.put(('success', scan_results))
            except Exception as e:
                result_queue.put(('error', str(e)))
        
        # Запускаем в отдельном потоке
        scan_thread = threading.Thread(target=run_scan)
        scan_thread.daemon = True
        scan_thread.start()
        
        # Ждем завершения с динамическим таймаутом
        scan_thread.join(timeout=estimated_time)
        
        if scan_thread.is_alive():
            flash(f'Сканирование прервано по таймауту ({estimated_time:.0f} секунд). Подсеть слишком большая.', 'warning')
            return render_template('scan.html', scan_history=scan_history)
        
        # Получаем результаты
        if result_queue.empty():
            flash('Сканирование не вернуло результатов', 'error')
            return render_template('scan.html', scan_history=scan_history)
        
        status, result = result_queue.get()
        
        if status == 'error':
            flash(f'Ошибка сканирования: {result}', 'error')
            return render_template('scan.html', scan_history=scan_history)
        
        scan_results = result
        
        # Сохраняем запись о сканировании
        try:
            scan_record = ScanHistory(
                subnet_scanned=subnet,
                devices_found=len(scan_results),
                scan_type='manual',
                initiated_by='Администратор',
                vlan_id=vlan_id
            )
            db.session.add(scan_record)
            db.session.commit()
            
            # Обновляем историю
            scan_history = ScanHistory.query.order_by(ScanHistory.scan_date.desc()).limit(10).all()
            
        except Exception as e:
            print(f"❌ Ошибка сохранения истории сканирования: {e}")
        
        # Сохраняем результаты в сессии
        session['scan_results'] = {
            'subnet': subnet,
            'vlan_id': vlan_id,
            'results': scan_results,
            'timestamp': datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'),
            'scan_id': scan_record.id if 'scan_record' in locals() else None
        }
        
        if len(scan_results) > 0:
            flash(f'✅ Найдено {len(scan_results)} устройств в подсети {subnet}', 'success')
        else:
            flash(f'ℹ️ Устройства в подсети {subnet} не найдены', 'info')
        
        return redirect(url_for('scan_results'))
    
    return render_template('scan.html', scan_history=scan_history)

@app.route('/scan/results')
def scan_results():
    """Страница результатов сканирования"""
    scan_data = session.get('scan_results')
    if not scan_data:
        flash('Нет результатов сканирования. Запустите сканирование сначала.', 'warning')
        return redirect(url_for('scan_network'))
    
    scan_record = None
    if 'scan_id' in scan_data and scan_data['scan_id']:
        try:
            scan_record = ScanHistory.query.get(scan_data['scan_id'])
        except:
            pass
    
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
        try:
            from scanner import NetworkScanner
            
            scanner = NetworkScanner()
            
            # Определяем локальную сеть автоматически
            current_ip = socket.gethostbyname(socket.gethostname())
            parts = current_ip.split('.')
            subnet = f"{parts[0]}.{parts[1]}.{parts[2]}.0/24"
            
            flash(f'Автоматически определена подсеть: {subnet}', 'info')
            
            # Запускаем быстрое сканирование
            print(f"⚡ Быстрое сканирование подсети: {subnet}")
            
            scan_results = scanner.quick_scan(subnet)
            
            # Сохраняем запись о сканировании
            scan_record = ScanHistory(
                subnet_scanned=subnet,
                devices_found=len(scan_results),
                scan_type='quick',
                initiated_by='Система'
            )
            db.session.add(scan_record)
            db.session.commit()
            
            # Сохраняем результаты в сессии
            session['scan_results'] = {
                'subnet': subnet,
                'vlan_id': None,
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
            flash(f'Не удалось выполнить быстрое сканирование: {str(e)}', 'error')
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

@app.route('/api/network/check')
def check_network():
    """API для проверки доступности сети"""
    try:
        from scanner import NetworkScanner
        scanner = NetworkScanner()
        
        result = scanner.check_network_connectivity()
        
        return jsonify({
            'success': result['success'],
            'gateway': result['gateway'],
            'message': result['message']
        })
            
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Ошибка: {str(e)}'
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
    with app.app_context():
        try:
            # Создаем таблицы, если их нет
            db.create_all()
            print("✅ Таблицы базы данных проверены")
        except Exception as e:
            print(f"⚠️  Ошибка при создании таблиц: {e}")
    
    if not wait_for_database():
        print("⚠️  Предупреждение: База данных недоступна, но приложение запускается")
    
    print("🚀 Запуск IT Inventory System...")
    print(f"📊 База данных: {Config.DB_HOST}:{Config.DB_PORT}/{Config.DB_NAME}")
    print(f"🌐 Приложение доступно по адресу: http://0.0.0.0:5000")
    
    app.run(host='0.0.0.0', port=5000, debug=True)