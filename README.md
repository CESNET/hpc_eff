# hpc_eff

**Energy Optimization Governor** for HPC systems.  
Dynamically adjusts CPU frequencies based on power, electricity price, CO₂ intensity, and temperature. Which signals drive the decision is fully configurable, and you can plug in your own temperature/data source.

All the functionality and code logic located in `src/hpc_eff` stem from https://gitlab.cesnet.cz/dexter/hpc_eff.

---

## Overview

`hpc_eff` is designed to be run periodically (e.g., via `cron` every few minutes) under root.  
It evaluates current energy/thermal conditions, prints debug logs if enabled, and sets the min and max CPU frequencies accordingly.

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

Steps 2–7 run only when the price/CO₂ regulator is enabled, and step 9 runs only when the temperature regulator is enabled (see **Regulation modes** below) — data that a disabled regulator would need is not gathered.

---

## Regulation modes

Two independent regulators are controlled by flags in the `[FEATURES]` section of the config. Either, both, or neither may be active:

```ini
[FEATURES]
# price/CO₂ → rating (1–10) → CPU max-frequency cap
ENABLE_SET_CPU = yes
# temperature → hysteresis-based CPU max-frequency control
ENABLE_CPU_THERMO = no
```

- **Price/CO₂ only** — `ENABLE_SET_CPU=yes`, `ENABLE_CPU_THERMO=no` (classic energy governor).
- **Temperature only** — `ENABLE_SET_CPU=no`, `ENABLE_CPU_THERMO=yes`.
- **Both** — when both are on, temperature acts as a hard limit: if the reading exceeds `[TEMPERATURE] THRESHOLD`, the rating is forced to 10 (lowest frequency).

### Temperature source ("bring your own reader")

The temperature reading is pluggable via `[TEMPERATURE_SOURCE]`:

```ini
[TEMPERATURE_SOURCE]
# TYPE can be: ipmi | http_api | custom
TYPE = ipmi
IPMI_SENSOR_NAME = INLET_AIR_TEMP

# HTTP API example:
# TYPE = http_api
# HTTP_URL = http://192.168.1.100/api/temperature
# HTTP_JSON_PATH = temperature.value   # optional dotted path into JSON

# Custom reader example — point at your own script/module:
# TYPE = custom
# MODULE = /opt/mysensors/my_reader.py  # file path OR importable dotted module name
# FUNCTION = read                       # optional, defaults to "read"
```

For `TYPE=custom`, your module just needs to expose a callable that returns a temperature in Celsius (a number), e.g.:

```python
def read():
    return 42.5
```

This lets you read from any sensor or data source (a rack PDU API, a cooling-loop probe, a site-specific script) without modifying `hpc_eff` itself.

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

Clone the repository first:
```bash
git clone git@github.com:CESNET/hpc_eff.git
cd hpc_eff
```

Then build and install using the packaging for your distribution.

### Option A — RPM (Fedora / RHEL / Rocky)

```bash
# dependencies
sudo dnf install ipmitool cpufrequtils make kernel-tools rpm-build rpmdevtools -y
# build and install
make
```

### Option B — DEB (Debian / Ubuntu)

```bash
# build dependencies
sudo apt update
sudo apt install build-essential devscripts debhelper dh-make dh-python python3-all python3-setuptools fakeroot
# runtime dependencies
sudo apt install ipmitool cpufrequtils python3-numpy python3-requests
# build the package
dpkg-buildpackage -us -uc
# install it
sudo dpkg -i ../hpc-eff_0.1-1_*.deb
```

To clean up / remove the DEB package:
```bash
dpkg-buildpackage -tc
sudo dpkg -r hpc-eff
```

### After install (all distributions)

1. Configure with your API key from [nowtricity](https://www.nowtricity.com/):
    ```bash
    sudo vi /etc/hpc_eff/config.ini
    ```
2. Test the executable:
    ```bash
    sudo hpc-eff
    ```
3. Enable or disable the system cronjob using command-line switches:
    ```bash
    hpc-eff --enable
    hpc-eff --disable
    ```
    By default, the cronjob runs every 10 minutes and is installed at `/etc/cron.d/hpc-eff`.
    You can customize the path and interval:
    ```bash
    hpc-eff --enable --cron-path /custom/path --cron-interval 5
    ```
4. To read from the created database:
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
