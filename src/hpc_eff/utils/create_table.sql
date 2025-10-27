CREATE TABLE IF NOT EXISTS cpu_settings_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    hostname TEXT NOT NULL,
    freq_min INTEGER,
    freq_max INTEGER
);
