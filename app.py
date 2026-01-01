from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, session
from flask_login import LoginManager, UserMixin, login_user, logout_user, current_user, login_required
from werkzeug.security import generate_password_hash, check_password_hash
from config import Config
from datetime import datetime
import socket
import time
import sys
import ipaddress
import re

# Сначала создаем Flask app
app = Flask(__name__)
app.config.from_object(Config)
app.secret_key = Config.SECRET_KEY

# Инициализация Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'index'
login_manager.login_message = 'Пожалуйста, войдите в систему для доступа к этой странице.'
login_manager.login_message_category = 'warning'

# Теперь импортируем db и инициализируем
from models import db

# Инициализация базы данных с приложением
db.init_app(app)

# Импортируем модели для регистрации
from models import Equipment, ScanHistory, User

def get_guest_user():
    """Создает гостевого пользователя"""
    class GuestUser(UserMixin):
        id = 0
        username = 'Гость'
        role = 'guest'
        department = None
        full_name = 'Гостевой доступ'

        @property
        def is_authenticated(self):
            return True

        @property
        def is_active(self):
            return True

        @property
        def is_anonymous(self):
            return False

        def get_id(self):
            return str(self.id)

    return GuestUser()

@login_manager.user_loader
def load_user(user_id):
    """Загрузчик пользователя для Flask-Login"""
    if user_id == '0':  # Гостевой пользователь
        return get_guest_user()
    return User.query.get(int(user_id))

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

def role_required(roles):
    """Декоратор для проверки ролей пользователя"""
    def decorator(f):
        @login_required
        def decorated_function(*args, **kwargs):
            if current_user.role not in roles:
                flash('Доступ запрещен. У вас недостаточно прав.', 'danger')
                return redirect(url_for('dashboard'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

@app.route('/')
def index():
    """Главная страница с регистрацией и входом"""
    if current_user.is_authenticated and current_user.id != 0:
        return redirect(url_for('dashboard'))
    return render_template('index.html')

@app.route('/login', methods=['POST'])
def login():
    """Аутентификация пользователя"""
    if current_user.is_authenticated and current_user.id != 0:
        return redirect(url_for('dashboard'))

    username = request.form.get('username')
    password = request.form.get('password')

    if not username or not password:
        flash('Пожалуйста, заполните все поля', 'warning')
        return redirect(url_for('index'))

    user = User.query.filter_by(username=username).first()

    if user and check_password_hash(user.password, password):
        login_user(user, remember=True)
<<<<<<< HEAD
=======
        # Убрали обновление last_login
>>>>>>> a8fea06af094240c9b7666caa4c185a29ac87a50
        flash(f'Добро пожаловать, {user.full_name}!', 'success')
        return redirect(url_for('dashboard'))

    flash('Неверный логин или пароль', 'danger')
    return redirect(url_for('index'))

@app.route('/register', methods=['POST'])
def register():
    """Регистрация нового пользователя"""
    if current_user.is_authenticated and current_user.id != 0:
        return redirect(url_for('dashboard'))

    username = request.form.get('username')
    password = request.form.get('password')
    confirm_password = request.form.get('confirm_password')
    full_name = request.form.get('full_name')
    department = request.form.get('department')
    role = request.form.get('role', 'other')

    # Проверки
    if password != confirm_password:
        flash('Пароли не совпадают', 'danger')
        return redirect(url_for('index'))

    if len(password) < 6:
        flash('Пароль должен содержать минимум 6 символов', 'danger')
        return redirect(url_for('index'))

    existing_user = User.query.filter_by(username=username).first()
    if existing_user:
        flash('Пользователь с таким логином уже существует', 'danger')
        return redirect(url_for('index'))

    # Создаем пользователя
    hashed_password = generate_password_hash(password)
    new_user = User(
        username=username,
        password=hashed_password,
        full_name=full_name,
        department=department,
        role=role,
        created_at=datetime.utcnow()
    )

    try:
        db.session.add(new_user)
        db.session.commit()
        flash('Регистрация успешна! Теперь войдите в систему', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Ошибка при регистрации: {str(e)}', 'danger')

    return redirect(url_for('index'))

@app.route('/guest_login', methods=['POST'])
def guest_login():
    """Вход как гость"""
    if current_user.is_authenticated:
        logout_user()

    guest_user = get_guest_user()
    login_user(guest_user, remember=False)

    flash('Вы вошли как гость. Функции редактирования недоступны', 'info')
    return redirect(url_for('dashboard'))

@app.route('/dashboard')
@login_required
def dashboard():
    """Главная панель управления"""
    try:
        # Разная логика для разных ролей
        if current_user.role == 'it':
            # IT видит все оборудование
            total_devices = Equipment.query.count()
            active_devices = Equipment.query.filter_by(is_active=True).count()
            recent_equipment = Equipment.query.order_by(Equipment.last_seen.desc()).limit(10).all()
        elif current_user.role == 'other':
            # Другие отделы видят только свое оборудование
            total_devices = Equipment.query.filter_by(department=current_user.department).count()
            active_devices = Equipment.query.filter_by(
                department=current_user.department,
                is_active=True
            ).count()
            recent_equipment = Equipment.query.filter_by(
                department=current_user.department
            ).order_by(Equipment.last_seen.desc()).limit(10).all()
        else:  # guest
            # Гости видят все, но только для просмотра
            total_devices = Equipment.query.count()
            active_devices = Equipment.query.filter_by(is_active=True).count()
            recent_equipment = Equipment.query.order_by(Equipment.last_seen.desc()).limit(10).all()

        # Получаем историю сканирований
        recent_scans = ScanHistory.query.order_by(ScanHistory.scan_date.desc()).limit(5).all()

    except Exception as e:
        print(f"Ошибка базы данных: {e}")
        total_devices = 0
        active_devices = 0
        recent_scans = []
        recent_equipment = []
        flash(f'Ошибка подключения к базе данных: {e}', 'error')

    return render_template('dashboard.html',
                         total_devices=total_devices,
                         active_devices=active_devices,
                         recent_scans=recent_scans,
                         recent_equipment=recent_equipment)

@app.route('/logout')
@login_required
def logout():
    """Выход из системы"""
    logout_user()
    flash('Вы вышли из системы', 'info')
    return redirect(url_for('index'))

@app.route('/equipment')
@login_required
def equipment_list():
    """Список всего оборудования с пагинацией"""
    try:
        search = request.args.get('search', '')
        page = request.args.get('page', 1, type=int)
        per_page = 20

        # Фильтруем по ролям
        if current_user.role == 'it':
            query = Equipment.query
        elif current_user.role == 'other':
            query = Equipment.query.filter_by(department=current_user.department)
        else:  # guest
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
@login_required
def equipment_detail(equipment_id):
    """Детальная информация об оборудовании"""
    try:
        equipment = Equipment.query.get_or_404(equipment_id)

        # Проверка прав доступа для non-IT пользователей
        if current_user.role == 'other' and equipment.department != current_user.department:
            flash('Доступ к этому оборудованию запрещен', 'danger')
            return redirect(url_for('equipment_list'))

        return render_template('equipment_detail.html', equipment=equipment)
    except Exception as e:
        flash(f'Ошибка загрузки оборудования: {e}', 'error')
        return redirect(url_for('equipment_list'))

@app.route('/equipment/<int:equipment_id>/edit', methods=['GET', 'POST'])
@login_required
def equipment_edit(equipment_id):
    """Редактирование оборудования"""
    equipment = Equipment.query.get_or_404(equipment_id)

    # Проверка прав доступа
    if current_user.role == 'guest':
        flash('Гостям запрещено редактировать оборудование', 'warning')
        return redirect(url_for('equipment_detail', equipment_id=equipment_id))

    if current_user.role == 'other' and equipment.department != current_user.department:
        flash('Доступ к редактированию этого оборудования запрещен', 'danger')
        return redirect(url_for('equipment_detail', equipment_id=equipment_id))

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
@login_required
@role_required(['it'])
def equipment_delete(equipment_id):
    """Удаление оборудования (мягкое удаление) - только для IT"""
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
@login_required
def equipment_add():
    """Добавление нового оборудования вручную"""
    if current_user.role == 'guest':
        flash('Гостям запрещено добавлять оборудование', 'warning')
        return redirect(url_for('equipment_list'))

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
                department=request.form.get('department', '').strip() or (current_user.department if current_user.role == 'other' else None),
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
@login_required
def scan_network():
    """Страница сканирования сети"""
    if current_user.role == 'guest':
        flash('Гостям запрещено сканировать сеть', 'warning')
        return redirect(url_for('dashboard'))

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

        # Передаем приложение Flask в NetworkScanner
        scanner = NetworkScanner(app)

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
                initiated_by=current_user.full_name or current_user.username,
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
@login_required
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
@login_required
def quick_scan():
    """Быстрое сканирование (только несколько адресов)"""
    if current_user.role == 'guest':
        flash('Гостям запрещено сканировать сеть', 'warning')
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        try:
            from scanner import NetworkScanner

            # Передаем приложение Flask в NetworkScanner
            scanner = NetworkScanner(app)

            # Определяем локальную сеть автоматически
            current_ip = socket.gethostbyname(socket.gethostname())
            parts = current_ip.split('.')
            subnet = f"{parts[0]}.{parts[1]}.{parts[2]}.0/24"

            flash(f'Автоматически определена подсеть: {subnet}', 'info')

            # Запускаем быстрое сканирование
            print(f"⚡ Быстрое сканирование подсети: {subnet}")

            scan_results = scanner.quick_scan(subnet)

            # Сохраняем запись о сканирования
            try:
                scan_record = ScanHistory(
                    subnet_scanned=subnet,
                    devices_found=len(scan_results),
                    scan_type='quick',
                    initiated_by=current_user.full_name or current_user.username
                )
                db.session.add(scan_record)
                db.session.commit()
            except Exception as e:
                print(f"❌ Ошибка сохранения истории сканирования: {e}")
                scan_record = None

            # Сохраняем результаты в сессии
            session['scan_results'] = {
                'subnet': subnet,
                'vlan_id': None,
                'results': scan_results,
                'timestamp': datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'),
                'scan_id': scan_record.id if scan_record else None
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
@login_required
def reports():
    """Страница с отчетами"""
    try:
        # Разные отчеты для разных ролей
        if current_user.role == 'it':
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
        elif current_user.role == 'other':
            # Только статистика по отделу пользователя
            dept_stats = [(current_user.department, Equipment.query.filter_by(
                department=current_user.department).count())]

            os_stats = db.session.query(
                Equipment.os_name,
                db.func.count(Equipment.id)
            ).filter_by(department=current_user.department).group_by(Equipment.os_name).all()

            vlan_stats = db.session.query(
                Equipment.vlan_id,
                db.func.count(Equipment.id)
            ).filter(
                Equipment.vlan_id.isnot(None),
                Equipment.department == current_user.department
            ).group_by(Equipment.vlan_id).all()
        else:  # guest
            flash('Гостям доступен только просмотр оборудования', 'info')
            return redirect(url_for('dashboard'))

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
@login_required
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
@login_required
def check_network():
    """API для проверки доступности сети"""
    if current_user.role == 'guest':
        return jsonify({
            'success': False,
            'message': 'Гостям запрещена проверка сети'
        }), 403

    try:
        from scanner import NetworkScanner
        # Передаем приложение Flask в NetworkScanner
        scanner = NetworkScanner(app)

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
            'users_count': User.query.count() if current_user.role == 'it' else 'hidden'
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

@app.route('/profile')
@login_required
def profile():
    """Профиль пользователя"""
    if current_user.role == 'guest':
        flash('Гостевой профиль не доступен', 'info')
        return redirect(url_for('dashboard'))
    return render_template('profile.html', user=current_user)

@app.route('/profile/edit', methods=['GET', 'POST'])
@login_required
def profile_edit():
    """Редактирование профиля пользователя"""
    if current_user.role == 'guest':
        flash('Гостевой профиль нельзя редактировать', 'warning')
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        try:
            current_user.full_name = request.form.get('full_name', '').strip()
            current_user.department = request.form.get('department', '').strip()

            # Смена пароля
            current_password = request.form.get('current_password', '').strip()
            new_password = request.form.get('new_password', '').strip()
            confirm_password = request.form.get('confirm_password', '').strip()

            if current_password and new_password:
                if not check_password_hash(current_user.password, current_password):
                    flash('Текущий пароль неверен', 'danger')
                    return redirect(url_for('profile_edit'))

                if new_password != confirm_password:
                    flash('Новые пароли не совпадают', 'danger')
                    return redirect(url_for('profile_edit'))

                if len(new_password) < 6:
                    flash('Новый пароль должен содержать минимум 6 символов', 'danger')
                    return redirect(url_for('profile_edit'))

                current_user.password = generate_password_hash(new_password)

            db.session.commit()
            flash('Профиль успешно обновлен', 'success')
            return redirect(url_for('profile'))

        except Exception as e:
            db.session.rollback()
            flash(f'Ошибка при обновлении профиля: {str(e)}', 'danger')
            return redirect(url_for('profile_edit'))

    return render_template('profile_edit.html', user=current_user)

@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_server_error(e):
    return render_template('500.html'), 500

if __name__ == '__main__':
    # Создаем контекст приложения для создания таблиц
    with app.app_context():
        try:
            # Создаем таблицы, если их нет
            db.create_all()

<<<<<<< HEAD
            # Создаем тестового IT-пользователя если его нет
            if not User.query.filter_by(username='admin').first():
=======
            # Проверяем наличие колонки last_login в таблице user
            # Если её нет, добавляем
            try:
                from sqlalchemy import inspect, text
                inspector = inspect(db.engine)
                columns = [col['name'] for col in inspector.get_columns('user')]

                if 'last_login' not in columns:
                    print("⚠️  Колонка last_login отсутствует, добавляем...")
                    db.session.execute(text('ALTER TABLE "user" ADD COLUMN last_login TIMESTAMP'))
                    db.session.commit()
                    print("✅ Колонка last_login добавлена")
            except Exception as e:
                print(f"⚠️  Не удалось проверить/добавить колонку last_login: {e}")

            # Создаем тестового IT-пользователя если его нет
            if not User.query.filter_by(username='admin').first():
                from werkzeug.security import generate_password_hash
>>>>>>> a8fea06af094240c9b7666caa4c185a29ac87a50
                admin_user = User(
                    username='admin',
                    password=generate_password_hash('admin123'),
                    full_name='Администратор',
                    department='IT',
                    role='it',
                    created_at=datetime.utcnow()
                )
                db.session.add(admin_user)
                db.session.commit()
                print("✅ Создан администратор по умолчанию: admin/admin123")

            print("✅ Таблицы базы данных проверены")
        except Exception as e:
            print(f"⚠️  Ошибка при создании таблиц: {e}")
<<<<<<< HEAD

    if not wait_for_database():
        print("⚠️  Предупреждение: База данных недоступна, но приложение запускается")

    print("🚀 Запуск IT Inventory System...")
    print(f"📊 База данных: {Config.DB_HOST}:{Config.DB_PORT}/{Config.DB_NAME}")
    print(f"👤 Система аутентификации: ВКЛ")
    print(f"🌐 Приложение доступно по адресу: http://0.0.0.0:5000")

    # Убедимся, что Flask слушает на всех интерфейсах
    app.run(host='0.0.0.0', port=5000, debug=False)  # debug=False для продакшн
=======
>>>>>>> a8fea06af094240c9b7666caa4c185a29ac87a50
