from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime

db = SQLAlchemy()

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    full_name = db.Column(db.String(200))
    department = db.Column(db.String(100))
    role = db.Column(db.String(20), default='other')  # 'it', 'other', 'guest'
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    # Убираем last_login, так как его нет в базе данных

    def __repr__(self):
        return f'<User {self.username}>'

class Equipment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ip_address = db.Column(db.String(45), unique=True, nullable=False)
    hostname = db.Column(db.String(255))
    mac_address = db.Column(db.String(17))
    vlan_id = db.Column(db.Integer)
    department = db.Column(db.String(100))
    inventory_number = db.Column(db.String(100))
    location = db.Column(db.String(200))
    responsible_person = db.Column(db.String(200))
    is_active = db.Column(db.Boolean, default=True)
    first_discovered = db.Column(db.DateTime, default=datetime.utcnow)
    last_seen = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    os_name = db.Column(db.String(100))
    os_version = db.Column(db.String(50))
    open_ports = db.Column(db.Text)
    device_type = db.Column(db.String(100))
    device_vendor = db.Column(db.String(100))
    uptime = db.Column(db.String(50))
    last_boot = db.Column(db.DateTime)
    cpu_usage = db.Column(db.Float)
    memory_usage = db.Column(db.Float)
    disk_usage = db.Column(db.Float)
    network_interfaces = db.Column(db.Text)
    additional_info = db.Column(db.Text)

    # Связь с пользователем
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)

    def __repr__(self):
        return f'<Equipment {self.hostname} ({self.ip_address})>'

class ScanHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    subnet_scanned = db.Column(db.String(100), nullable=False)
    devices_found = db.Column(db.Integer, default=0)
    scan_date = db.Column(db.DateTime, default=datetime.utcnow)
    scan_type = db.Column(db.String(50))  # manual, quick, scheduled
    initiated_by = db.Column(db.String(100))
    vlan_id = db.Column(db.Integer, nullable=True)

    def __repr__(self):
        return f'<ScanHistory {self.subnet_scanned} - {self.devices_found} devices>'

# Дополнительные модели для учета расходных материалов
class Consumable(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    category = db.Column(db.String(100))
    unit = db.Column(db.String(50))
    current_quantity = db.Column(db.Integer, default=0)
    min_quantity = db.Column(db.Integer, default=10)
    location = db.Column(db.String(200))
    supplier = db.Column(db.String(200))
    notes = db.Column(db.Text)
    department = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f'<Consumable {self.name}>'

class ConsumableTransaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    consumable_id = db.Column(db.Integer, db.ForeignKey('consumable.id'))
    transaction_type = db.Column(db.String(20))
    quantity = db.Column(db.Integer)
    date = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    notes = db.Column(db.Text)
    department = db.Column(db.String(100))

    def __repr__(self):
        return f'<ConsumableTransaction {self.transaction_type} {self.quantity}>'
