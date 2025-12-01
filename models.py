from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class Equipment(db.Model):
    __tablename__ = 'equipment'
    
    id = db.Column(db.Integer, primary_key=True)
    ip_address = db.Column(db.String(15), unique=True, nullable=False)
    mac_address = db.Column(db.String(17))
    hostname = db.Column(db.String(100))
    
    # System Information
    os_name = db.Column(db.String(100))
    os_version = db.Column(db.String(50))
    architecture = db.Column(db.String(20))
    
    # Hardware Information
    cpu_model = db.Column(db.String(100))
    cpu_cores = db.Column(db.Integer)
    ram_total = db.Column(db.String(20))
    storage_info = db.Column(db.Text)
    gpu_info = db.Column(db.Text)
    
    # Network Information
    subnet = db.Column(db.String(20))
    vlan_id = db.Column(db.Integer)
    switch_port = db.Column(db.String(50))
    
    # Administrative Information
    inventory_number = db.Column(db.String(50))
    location = db.Column(db.String(100))
    department = db.Column(db.String(100))
    responsible_person = db.Column(db.String(100))
    warranty_until = db.Column(db.Date)
    
    # Timestamps
    first_discovered = db.Column(db.DateTime, default=datetime.utcnow)
    last_seen = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)
    
    def to_dict(self):
        return {
            'id': self.id,
            'ip_address': self.ip_address,
            'mac_address': self.mac_address,
            'hostname': self.hostname,
            'os_name': self.os_name,
            'os_version': self.os_version,
            'cpu_model': self.cpu_model,
            'ram_total': self.ram_total,
            'vlan_id': self.vlan_id,
            'inventory_number': self.inventory_number,
            'location': self.location,
            'last_seen': self.last_seen.isoformat() if self.last_seen else None
        }

class ScanHistory(db.Model):
    __tablename__ = 'scan_history'
    
    id = db.Column(db.Integer, primary_key=True)
    subnet_scanned = db.Column(db.String(20), nullable=False)
    devices_found = db.Column(db.Integer)
    scan_type = db.Column(db.String(20))  # 'auto', 'manual'
    scan_date = db.Column(db.DateTime, default=datetime.utcnow)
    initiated_by = db.Column(db.String(100))
