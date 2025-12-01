import subprocess
import socket
import platform
import ipaddress
import psutil
from datetime import datetime
import random
from models import db, Equipment
import concurrent.futures

class NetworkScanner:
    def __init__(self):
        self.results = []
    
    def validate_subnet(self, subnet):
        """Проверяет корректность подсети"""
        try:
            network = ipaddress.ip_network(subnet, strict=False)
            return network
        except ValueError as e:
            raise ValueError(f"Некорректная подсеть: {e}")
    
    def ping_host(self, ip):
        """Пинг конкретного IP"""
        try:
            param = '-n' if platform.system().lower() == 'windows' else '-c'
            result = subprocess.run(
                ['ping', param, '1', '-w', '500', str(ip)],
                capture_output=True,
                text=True,
                timeout=1
            )
            return result.returncode == 0
        except:
            return False
    
    def get_host_info(self, ip):
        """Получает информацию об устройстве"""
        try:
            # Пытаемся получить имя хоста
            try:
                hostname = socket.gethostbyaddr(str(ip))[0]
            except:
                hostname = "Неизвестно"
            
            # Получаем MAC-адрес
            mac_address = self._get_mac_address(str(ip))
            
            # Определяем ОС
            os_type = self._detect_os(str(ip))
            
            return {
                'ip_address': str(ip),
                'hostname': hostname,
                'mac_address': mac_address,
                'os_name': os_type,
                'status': 'online',
                'last_seen': datetime.utcnow()
            }
        except Exception as e:
            print(f"Ошибка при получении информации о {ip}: {e}")
            return None
    
    def _get_mac_address(self, ip):
        """Получает MAC-адрес (упрощенная версия)"""
        # В реальном приложении здесь будет ARP-запрос
        # Генерируем случайный MAC для демонстрации
        return ':'.join(['%02x' % random.randint(0, 255) for _ in range(6)])
    
    def _detect_os(self, ip):
        """Определяет ОС по открытым портам"""
        ports_to_check = [
            (22, "Linux/Unix"),
            (23, "Network Device"),
            (80, "Web Server"),
            (135, "Windows"),
            (139, "Windows"),
            (445, "Windows"),
            (3389, "Windows")
        ]
        
        try:
            for port, os_name in ports_to_check:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(0.5)
                result = sock.connect_ex((ip, port))
                sock.close()
                
                if result == 0:
                    return os_name
        except:
            pass
        
        return "Неизвестно"
    
    def scan_subnet(self, subnet, vlan_id=None, max_threads=50):
        """Сканирует подсеть"""
        try:
            network = self.validate_subnet(subnet)
        except ValueError as e:
            raise ValueError(e)
        
        print(f"🔍 Сканирование подсети: {subnet}, VLAN: {vlan_id}")
        print(f"📡 Проверка {network.num_addresses - 2} хостов...")
        
        # Получаем все IP в подсети
        hosts = list(network.hosts())
        
        # Ограничиваем количество хостов для больших сетей
        if len(hosts) > 1000:
            hosts = hosts[:1000]  # Сканируем только первые 1000 хостов
            print(f"⚠️  Большая подсеть, сканируем только первые 1000 хостов")
        
        # Многопоточное сканирование
        found_devices = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_threads) as executor:
            future_to_ip = {executor.submit(self.ping_host, ip): ip for ip in hosts}
            
            for future in concurrent.futures.as_completed(future_to_ip):
                ip = future_to_ip[future]
                if future.result():  # Если хост доступен
                    device_info = self.get_host_info(ip)
                    if device_info:
                        found_devices.append(device_info)
                        print(f"✅ Найден: {device_info['ip_address']} ({device_info['hostname']})")
        
        # Сохраняем результаты в базу
        self._save_to_database(found_devices, vlan_id)
        
        print(f"🎯 Сканирование завершено. Найдено: {len(found_devices)} устройств")
        return found_devices
    
    def _save_to_database(self, devices, vlan_id=None):
        """Сохраняет найденные устройства в базу"""
        saved_count = 0
        
        for device in devices:
            try:
                # Проверяем, существует ли уже устройство
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
                    new_equipment = Equipment(
                        ip_address=device['ip_address'],
                        hostname=device['hostname'],
                        mac_address=device['mac_address'],
                        os_name=device['os_name'],
                        vlan_id=vlan_id,
                        last_seen=device['last_seen'],
                        is_active=True
                    )
                    db.session.add(new_equipment)
                
                saved_count += 1
                
            except Exception as e:
                print(f"❌ Ошибка сохранения устройства {device['ip_address']}: {e}")
                db.session.rollback()
        
        try:
            db.session.commit()
            print(f"💾 Сохранено {saved_count} устройств в базу данных")
        except Exception as e:
            print(f"❌ Ошибка коммита в базу данных: {e}")
            db.session.rollback()