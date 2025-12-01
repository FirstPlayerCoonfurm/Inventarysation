# models.py - обновленная модель Equipment
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class Equipment(db.Model):
    __tablename__ = 'equipment'
    
    id = db.Column(db.Integer, primary_key=True)
    ip_address = db.Column(db.String(15), nullable=False, unique=True, index=True)
    hostname = db.Column(db.String(255))
    mac_address = db.Column(db.String(17))
    vlan_id = db.Column(db.Integer)
    os_name = db.Column(db.String(100))
    os_version = db.Column(db.String(50))
    department = db.Column(db.String(100))
    inventory_number = db.Column(db.String(50))
    serial_number = db.Column(db.String(100))
    model = db.Column(db.String(100))
    manufacturer = db.Column(db.String(100))
    location = db.Column(db.String(255))
    responsible_person = db.Column(db.String(100))
    description = db.Column(db.Text)
    is_active = db.Column(db.Boolean, default=True)
    first_discovered = db.Column(db.DateTime, default=datetime.utcnow)
    last_seen = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    deleted_at = db.Column(db.DateTime)
    
    def __repr__(self):
        return f'<Equipment {self.ip_address} - {self.hostname}>'

# ScanHistory остается без изменений
class ScanHistory(db.Model):
    __tablename__ = 'scan_history'
    id = db.Column(db.Integer, primary_key=True)
    subnet_scanned = db.Column(db.String(50), nullable=False)
    devices_found = db.Column(db.Integer, default=0)
    scan_date = db.Column(db.DateTime, default=datetime.utcnow)
    scan_type = db.Column(db.String(20))  # manual, scheduled, quick
    initiated_by = db.Column(db.String(100))
    vlan_id = db.Column(db.Integer)
    
    def __repr__(self):
        return f'<ScanHistory {self.subnet_scanned} - {self.scan_date}>'