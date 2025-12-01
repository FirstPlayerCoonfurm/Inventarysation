import subprocess
import socket
import platform
import ipaddress
from datetime import datetime
import threading
import concurrent.futures
import time
from models import db, Equipment

class NetworkScanner:
    def __init__(self):
        self.scanning = False
        self.progress = 0
        self.found_devices = []
    
    def validate_subnet(self, subnet):
        """Проверяет корректность подсети"""
        try:
            network = ipaddress.ip_network(subnet, strict=False)
            return network
        except ValueError as e:
            raise ValueError(f"Некорректная подсеть: {e}")
    
    def ping_host(self, ip, timeout=1):
        """Улучшенный ping с обработкой ошибок"""
        try:
            # Для Linux/macOS
            if platform.system().lower() != 'windows':
                cmd = ['ping', '-c', '1', '-W', str(timeout), str(ip)]
            else:
                cmd = ['ping', '-n', '1', '-w', str(timeout * 1000), str(ip)]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout + 1
            )
            
            # Проверяем успешный ping
            if platform.system().lower() != 'windows':
                return result.returncode == 0 and "1 received" in result.stdout
            else:
                return result.returncode == 0 and "TTL=" in result.stdout
                
        except (subprocess.TimeoutExpired, Exception):
            return False
    
    def get_mac_address(self, ip):
        """Получает реальный MAC-адрес через ARP"""
        try:
            # Для Linux
            if platform.system().lower() == 'linux':
                # Попробуем получить из ARP таблицы
                result = subprocess.run(
                    ['arp', '-n', str(ip)],
                    capture_output=True,
                    text=True
                )
                
                if result.returncode == 0 and result.stdout:
                    lines = result.stdout.strip().split('\n')
                    for line in lines:
                        if str(ip) in line:
                            parts = line.split()
                            if len(parts) >= 3:
                                mac = parts[2]
                                if ':' in mac or '-' in mac:
                                    return mac.replace('-', ':')
            
            # Для Windows
            elif platform.system().lower() == 'windows':
                result = subprocess.run(
                    ['arp', '-a', str(ip)],
                    capture_output=True,
                    text=True,
                    encoding='cp866'
                )
                
                if result.returncode == 0 and result.stdout:
                    lines = result.stdout.strip().split('\n')
                    for line in lines:
                        if str(ip) in line:
                            parts = line.split()
                            for part in parts:
                                if ':' in part or '-' in part:
                                    return part.replace('-', ':')
            
            # Если не нашли, возвращаем неизвестно
            return "Неизвестно"
            
        except Exception:
            return "Неизвестно"
    
    def get_hostname(self, ip):
        """Получает имя хоста"""
        try:
            hostname = socket.getfqdn(ip)
            if hostname == ip:
                return "Неизвестно"
            return hostname
        except:
            return "Неизвестно"
    
    def detect_os(self, ip):
        """Определяет ОС по характерным признакам"""
        # Упрощенная детекция - проверяем только несколько портов
        ports_to_check = [
            (22, "Linux/Unix (SSH)"),
            (3389, "Windows (RDP)"),
            (445, "Windows (SMB)"),
            (80, "Веб-сервер"),
            (443, "Веб-сервер (HTTPS)")
        ]
        
        for port, os_name in ports_to_check:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(1)
                result = sock.connect_ex((str(ip), port))
                sock.close()
                
                if result == 0:
                    return os_name
            except:
                continue
        
        return "Неизвестно"
    
    def scan_single_host(self, ip, vlan_id=None):
        """Сканирует один хост"""
        try:
            # Проверяем доступность
            if not self.ping_host(ip, timeout=1):
                return None
            
            # Получаем информацию
            hostname = self.get_hostname(ip)
            mac_address = self.get_mac_address(ip)
            os_name = self.detect_os(ip)
            
            device_info = {
                'ip_address': str(ip),
                'hostname': hostname,
                'mac_address': mac_address,
                'os_name': os_name,
                'status': 'online',
                'last_seen': datetime.utcnow(),
                'vlan_id': vlan_id
            }
            
            print(f"✅ Найден: {ip} ({hostname}) - {os_name}")
            return device_info
            
        except Exception as e:
            print(f"❌ Ошибка сканирования {ip}: {e}")
            return None
    
    def scan_subnet(self, subnet, vlan_id=None, max_threads=10, timeout=2):
        """Сканирует подсеть с ограничениями"""
        self.scanning = True
        self.found_devices = []
        
        try:
            network = self.validate_subnet(subnet)
        except ValueError as e:
            raise ValueError(e)
        
        print(f"🔍 Начинаем сканирование подсети: {subnet}")
        print(f"📡 Всего адресов: {network.num_addresses}")
        
        # Ограничиваем количество сканируемых адресов
        hosts = list(network.hosts())
        max_hosts = 256  # Максимум 256 адресов
        if len(hosts) > max_hosts:
            hosts = hosts[:max_hosts]
            print(f"⚠️  Ограничение: сканируем только первые {max_hosts} адресов")
        
        total_hosts = len(hosts)
        print(f"🔢 Будет сканироваться: {total_hosts} хостов")
        
        # Многопоточное сканирование с прогрессом
        found_devices = []
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_threads) as executor:
            # Запускаем задачи
            future_to_ip = {executor.submit(self.scan_single_host, ip, vlan_id): ip for ip in hosts}
            
            completed = 0
            for future in concurrent.futures.as_completed(future_to_ip):
                completed += 1
                ip = future_to_ip[future]
                
                # Обновляем прогресс каждые 10 хостов
                if completed % 10 == 0 or completed == total_hosts:
                    print(f"📊 Прогресс: {completed}/{total_hosts} ({completed/total_hosts*100:.1f}%)")
                
                try:
                    device_info = future.result(timeout=timeout)
                    if device_info:
                        found_devices.append(device_info)
                except Exception as e:
                    print(f"⚠️  Ошибка при сканировании {ip}: {e}")
        
        # Сохраняем в базу
        saved_count = self.save_to_database(found_devices, vlan_id)
        
        print(f"🎯 Сканирование завершено!")
        print(f"✅ Найдено устройств: {len(found_devices)}")
        print(f"💾 Сохранено в базу: {saved_count}")
        
        self.scanning = False
        return found_devices
    
    def save_to_database(self, devices, vlan_id=None):
        """Сохраняет устройства в базу данных"""
        saved_count = 0
        
        for device in devices:
            try:
                # Ищем существующее устройство
                existing = Equipment.query.filter_by(ip_address=device['ip_address']).first()
                
                if existing:
                    # Обновляем существующее
                    existing.hostname = device['hostname']
                    existing.mac_address = device['mac_address']
                    existing.os_name = device['os_name']
                    existing.last_seen = device['last_seen']
                    existing.is_active = True
                    if vlan_id:
                        existing.vlan_id = vlan_id
                else:
                    # Создаем новое
                    new_eq = Equipment(
                        ip_address=device['ip_address'],
                        hostname=device['hostname'],
                        mac_address=device['mac_address'],
                        os_name=device['os_name'],
                        vlan_id=vlan_id,
                        last_seen=device['last_seen'],
                        is_active=True,
                        first_discovered=datetime.utcnow()
                    )
                    db.session.add(new_eq)
                
                saved_count += 1
                
            except Exception as e:
                print(f"❌ Ошибка сохранения {device['ip_address']}: {e}")
                db.session.rollback()
        
        try:
            db.session.commit()
            return saved_count
        except Exception as e:
            print(f"❌ Ошибка коммита в базу: {e}")
            db.session.rollback()
            return 0
    
    def quick_scan(self, subnet, vlan_id=None):
        """Быстрое сканирование - проверяет только ключевые адреса"""
        try:
            network = self.validate_subnet(subnet)
        except ValueError as e:
            raise ValueError(e)
        
        # Проверяем только определенные адреса
        common_addresses = [
            network.network_address + 1,  # Обычно шлюз
            network.network_address + 2,
            network.network_address + 10,
            network.network_address + 50,
            network.network_address + 100,
            network.broadcast_address - 1  # Последний адрес
        ]
        
        found_devices = []
        for ip in common_addresses:
            if ip in network:
                device = self.scan_single_host(ip, vlan_id)
                if device:
                    found_devices.append(device)
        
        return found_devices