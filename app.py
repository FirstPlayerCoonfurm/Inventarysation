from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, session
from models import db, Equipment, ScanHistory
from config import Config
from datetime import datetime
import socket
import time
import sys
import ipaddress
import re  # Добавлен для валидации MAC-адреса

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

def validate_mac_address(mac):
    """Валидация MAC-адреса"""
    if not mac:
        return True, None
    
    mac_pattern = re.compile(r'^([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})$')
    if mac_pattern.match(mac):
        # Стандартизируем формат
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
        department = request.args.get('department', '')
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
        
        if department:
            query = query.filter(Equipment.department == department)
        
        # Пагинация
        equipment_pagination = query.order_by(Equipment.last_seen.desc()).paginate(
            page=page, per_page=per_page, error_out=False
        )
        
        equipment = equipment_pagination.items
        
    except Exception as e:
        flash(f'Ошибка загрузки оборудования: {e}', 'error')
        equipment_pagination = None
        equipment = []
        search = ''
        department = ''

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
            # Получаем данные из формы
            equipment.hostname = request.form.get('hostname', '').strip() or None
            equipment.department = request.form.get('department', '').strip() or None
            equipment.inventory_number = request.form.get('inventory_number', '').strip() or None
            equipment.serial_number = request.form.get('serial_number', '').strip() or None
            equipment.model = request.form.get('model', '').strip() or None
            equipment.manufacturer = request.form.get('manufacturer', '').strip() or None
            equipment.os_name = request.form.get('os_name', '').strip() or None
            equipment.os_version = request.form.get('os_version', '').strip() or None
            equipment.description = request.form.get('description', '').strip() or None
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
                    # Стандартизируем формат
                    equipment.mac_address = mac_address.upper().replace('-', ':')
                else:
                    flash(error_msg, 'error')
                    return redirect(url_for('equipment_edit', equipment_id=equipment_id))
            else:
                equipment.mac_address = None
            
            # Обновляем дату последнего изменения
            equipment.updated_at = datetime.utcnow()
            
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
        
        # Мягкое удаление - помечаем как неактивное
        equipment.is_active = False
        equipment.deleted_at = datetime.utcnow()
        equipment.updated_at = datetime.utcnow()
        
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
            # Валидация обязательных полей
            ip_address = request.form.get('ip_address', '').strip()
            if not ip_address:
                flash('IP-адрес обязателен для заполнения', 'error')
                return redirect(url_for('equipment_add'))
            
            # Проверяем валидность IP
            try:
                ipaddress.ip_address(ip_address)
            except ValueError:
                flash('Некорректный IP-адрес', 'error')
                return redirect(url_for('equipment_add'))
            
            # Проверяем, существует ли уже оборудование с таким IP
            existing = Equipment.query.filter_by(ip_address=ip_address).first()
            if existing:
                flash(f'Оборудование с IP-адресом {ip_address} уже существует', 'error')
                return redirect(url_for('equipment_add'))
            
            # Валидация MAC-адреса
            mac_address = request.form.get('mac_address', '').strip()
            if mac_address:
                is_valid, error_msg = validate_mac_address(mac_address)
                if not is_valid:
                    flash(error_msg, 'error')
                    return redirect(url_for('equipment_add'))
                # Стандартизируем формат
                mac_address = mac_address.upper().replace('-', ':')
            
            # Создаем новое оборудование
            new_equipment = Equipment(
                ip_address=ip_address,
                hostname=request.form.get('hostname', '').strip() or None,
                mac_address=mac_address or None,
                department=request.form.get('department', '').strip() or None,
                inventory_number=request.form.get('inventory_number', '').strip() or None,
                serial_number=request.form.get('serial_number', '').strip() or None,
                model=request.form.get('model', '').strip() or None,
                manufacturer=request.form.get('manufacturer', '').strip() or None,
                os_name=request.form.get('os_name', '').strip() or None,
                os_version=request.form.get('os_version', '').strip() or None,
                description=request.form.get('description', '').strip() or None,
                location=request.form.get('location', '').strip() or None,
                responsible_person=request.form.get('responsible_person', '').strip() or None,
                is_active='is_active' in request.form,
                first_discovered=datetime.utcnow(),
                last_seen=datetime.utcnow()
            )
            
            # Валидация VLAN
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

# ... остальные маршруты остаются без изменений (scan_network, scan_results, quick_scan, reports и т.д.)

if __name__ == '__main__':
    with app.app_context():
        # Создаем таблицы, если их нет
        db.create_all()
        print("✅ Таблицы базы данных проверены/созданы")
    
    if not wait_for_database():
        print("⚠️  Предупреждение: База данных недоступна, но приложение запускается")
    
    print("🚀 Запуск IT Inventory System...")
    print(f"📊 База данных: {Config.DB_HOST}:{Config.DB_PORT}/{Config.DB_NAME}")
    print(f"🌐 Приложение доступно по адресу: http://0.0.0.0:5000")
    
    app.run(host='0.0.0.0', port=5000, debug=True)