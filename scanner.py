import subprocess
import socket
import platform
import psutil
from models import db, Equipment
from datetime import datetime

class NetworkScanner:
    def __init__(self):
        self.results = []
    
    def scan_subnet(self, subnet, vlan_id=None):
        """Сканирование подсети и обновление базы данных"""
        print(f"Сканирование подсети: {subnet}, VLAN: {vlan_id}")
        
        # Здесь используем код сканирования из предыдущих примеров
        devices = self._ping_sweep(subnet)
        
        for device in devices:
            self._update_equipment_database(device, vlan_id)
        
        return devices
    
    def _ping_sweep(self, subnet):
        """Сканирование подсети пингом"""
        devices = []
        network_prefix = '.'.join(subnet.split('.')[:-1]) + '.'
        
        for i in range(1, 255):
            ip = f"{network_prefix}{i}"
            if self._ping_host(ip):
                device_info = self._gather_device_info(ip)
                devices.append(device_info)
        
        return devices
    
    def _ping_host(self, ip):
        """Проверка доступности хоста"""
        try:
            param = '-n' if platform.system().lower() == 'windows' else '-c'
            result = subprocess.run(
                ['ping', param, '1', '-w', '1000', ip],
                capture_output=True,
                text=True,
                timeout=2
            )
            return result.returncode == 0
        except:
            return False
    
    def _gather_device_info(self, ip):
        """Сбор информации об устройстве"""
        try:
            hostname = socket.getfqdn(ip)
        except:
            hostname = "Неизвестно"
        
        return {
            'ip_address': ip,
            'hostname': hostname,
            'mac_address': self._get_mac_address(ip),
            'os_name': platform.system() if ip == '127.0.0.1' else "Неизвестно",
            'last_seen': datetime.utcnow()
        }
    
    def _get_mac_address(self, ip):
        """Получение MAC-адреса (упрощенная версия)"""
        # В реальном приложении здесь будет ARP-запрос
        return "00:00:00:00:00:00"
    
    def _update_equipment_database(self, device_info, vlan_id):
        """Обновление базы данных с информацией об оборудовании"""
        equipment = Equipment.query.filter_by(ip_address=device_info['ip_address']).first()
        
        if equipment:
            # Обновляем существующую запись
            equipment.hostname = device_info['hostname']
            equipment.mac_address = device_info['mac_address']
            equipment.last_seen = device_info['last_seen']
            equipment.is_active = True
        else:
            # Создаем новую запись
            equipment = Equipment(
                ip_address=device_info['ip_address'],
                hostname=device_info['hostname'],
                mac_address=device_info['mac_address'],
                vlan_id=vlan_id,
                last_seen=device_info['last_seen']
            )
            db.session.add(equipment)
        
        db.session.commit()
