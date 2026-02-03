# hpc_eff

**Energy Optimization Governor** for HPC systems.  
Dynamically adjusts CPU frequencies based on power, electricity price, CO₂ intensity, and temperature.
All the functionality and code logic located in `src/hpc_eff` stem from https://gitlab.cesnet.cz/dexter/hpc_eff.

---

## Overview

`hpc_eff` is designed to be run periodically (e.g., via `cron` every few minutes) under root.  
It evaluates current energy conditions, prints debug logs if enabled, and sets the min and max CPU frequencies accordingly.

**Main steps performed:**
1. Load configuration from `/etc/hpc_eff/config.ini`
2. Fetch current electricity price
3. Read current power usage via a configured shell command
4. Read current CPU frequency
5. Retrieve available CPU frequencies and governors
6. Fetch historical energy price averages and classify current price
7. Fetch last 24h CO₂ values and calculate rating
8. Add current evaluation data and history to a JSON state file (for external monitoring)
9. Apply temperature-based CPU frequency control
10. Apply min and max CPU frequencies based on rating

---

## Logging & Monitoring

The application maintains two types of logs:
- **SQLite Database**: Detailed historical logs stored at `/var/lib/hpc_eff/history.db`.
- **JSON State File**: A consolidated state file at `/var/lib/hpc_eff/state.json` containing:
    - `static`: System metadata (score, power command, active plugins).
    - `current`: Latest evaluation results (rating, price, power, temp, etc.).
    - `history`: A rolling history of previous evaluations.

These can be configured in `/etc/hpc_eff/config.ini`:
```ini
[logging]
db_path = /var/lib/hpc_eff/history.db
state_json_path = /var/lib/hpc_eff/state.json
history_length = 10
```

---

## Installation

1. Clone the repository:
   ```bash
   git clone git@github.com:CESNET/hpc_eff.git
   cd hpc_eff
   ```
2. Install the dependencies:
    ```bash
    sudo apt update
    sudo apt install build-essential devscripts debhelper dh-make dh-python python3-all python3-setuptools fakeroot
    sudo apt install ipmitool cpufrequtils python3-numpy python3-requests
    ```
3. Build the package:
    ```bash
    dpkg-buildpackage -us -uc
    ```
4. Install the package:
    ```bash
    sudo dpkg -i ../hpc-eff_0.1-1_*.deb
    ```
5. Test executable 
    ```bash
    sudo hpc-eff
    ```
6. Clean up (optional):
    ```bash
    dpkg-buildpackage -tc
    sudo dpkg -r hpc-eff
    ```
7. Configure with your API key from [nowtricity](https://www.nowtricity.com/):
    ```bash
    sudo vi /etc/hpc_eff/config.ini
    ```
8. You can enable or disable a system cronjob using command-line switches.
    ```bash
    hpc-eff --enable
    hpc-eff --disable

    ```
    By default, the cronjob runs every 10 minutes and is installed at /etc/cron.d/hpc-eff.
    You can customize the path and interval:
    ```bash
    hpc-eff --enable --cron-path /custom/path --cron-interval 5
    ```
9. To read from the created database:
    ```bash
    sudo cp /var/lib/hpc_eff/history.db ~/history.db
    sqlite3 ~/history.db
    ```
    Inspect tables and data:
    ```
    .tables
    .schema cpu_settings_log 
    SELECT * FROM cpu_settings_log LIMIT 10;
    ```
