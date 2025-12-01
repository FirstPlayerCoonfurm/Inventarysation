-- Создание таблицы equipment
CREATE TABLE IF NOT EXISTS equipment (
    id SERIAL PRIMARY KEY,
    ip_address VARCHAR(15) UNIQUE NOT NULL,
    mac_address VARCHAR(17),
    hostname VARCHAR(100),
    
    -- System Information
    os_name VARCHAR(100),
    os_version VARCHAR(50),
    architecture VARCHAR(20),
    
    -- Hardware Information
    cpu_model VARCHAR(100),
    cpu_cores INTEGER,
    ram_total VARCHAR(20),
    storage_info TEXT,
    gpu_info TEXT,
    
    -- Network Information
    subnet VARCHAR(20),
    vlan_id INTEGER,
    switch_port VARCHAR(50),
    
    -- Administrative Information
    inventory_number VARCHAR(50),
    location VARCHAR(100),
    department VARCHAR(100),
    responsible_person VARCHAR(100),
    warranty_until DATE,
    
    -- Timestamps
    first_discovered TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE
);

-- Создание таблицы scan_history с колонкой vlan_id
CREATE TABLE IF NOT EXISTS scan_history (
    id SERIAL PRIMARY KEY,
    subnet_scanned VARCHAR(50) NOT NULL,
    devices_found INTEGER,
    scan_type VARCHAR(20),
    scan_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    initiated_by VARCHAR(100),
    vlan_id INTEGER  -- Добавляем эту колонку
);

-- Создание индексов
CREATE INDEX IF NOT EXISTS idx_equipment_ip ON equipment(ip_address);
CREATE INDEX IF NOT EXISTS idx_equipment_hostname ON equipment(hostname);
CREATE INDEX IF NOT EXISTS idx_equipment_vlan ON equipment(vlan_id);
CREATE INDEX IF NOT EXISTS idx_equipment_last_seen ON equipment(last_seen);
CREATE INDEX IF NOT EXISTS idx_scan_history_date ON scan_history(scan_date);