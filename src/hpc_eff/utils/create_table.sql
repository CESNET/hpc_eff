CREATE TABLE IF NOT EXISTS cpu_settings_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    hostname TEXT NOT NULL,
    freq_min INTEGER,
    freq_max INTEGER,
    score_name TEXT,
    score_value REAL,
    price REAL,
    co2_current REAL,
    co2_median REAL,
    co2_grade TEXT,
    power_w REAL,
    cpu_freq_current INTEGER,
    rating INTEGER,
    rating_price INTEGER,
    rating_co2 INTEGER,
    temperature REAL
);
