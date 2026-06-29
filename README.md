# hpc_eff

**Energy Optimization Governor** for HPC systems.  
Dynamically adjusts CPU frequencies and GPU power based on power, electricity price, CO₂ intensity, and temperature. Which signals drive the decision is fully configurable, and you can plug in your own temperature/data source.

All the functionality and code logic located in `src/hpc_eff` stem from https://gitlab.cesnet.cz/dexter/hpc_eff.

---

## Overview

`hpc_eff` is designed to be run periodically (e.g., via `cron` every few minutes) under root.  
It evaluates current energy/thermal conditions, prints debug logs if enabled, and adjusts CPU frequencies and GPU power accordingly.

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
11. Regulate GPU power based on temperature (if enabled)

Steps 2–7 run only when the price/CO₂ regulator is enabled; steps 9 and 11 run only when their respective regulators are enabled (see [Regulation modes](#regulation-modes) below).

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
# dependencies (kernel-tools provides cpupower for setting CPU frequency)
sudo dnf install ipmitool make kernel-tools rpm-build rpmdevtools -y

# optional: for GPU power regulation (NVIDIA GPUs)
sudo dnf install nvidia-driver -y

# build and install
make
```

To clean up / remove the RPM package:
```bash
sudo rpm -e hpc_eff
# or, using the Makefile target:
make uninstall
```

### Option B — DEB (Debian / Ubuntu)

```bash
# build dependencies
sudo apt update
sudo apt install build-essential devscripts debhelper dh-make dh-python python3-all python3-setuptools fakeroot
# runtime dependencies
sudo apt install ipmitool linux-cpupower python3-numpy python3-requests

# optional: for GPU power regulation (NVIDIA GPUs)
sudo apt install nvidia-driver-dkms -y

# build the package (recommended)
make deb

# or manually:
# dpkg-buildpackage -us -uc

# install it
sudo dpkg -i ../hpc-eff_*.deb
# fix any missing dependencies if needed
sudo apt-get install -f
```

To clean up / remove the DEB package:
```bash
sudo dpkg -r hpc-eff
# or, to remove config files too:
sudo dpkg --purge hpc-eff
```

**Note:** RPM and DEB targets are independent. Use `make` on RHEL/AlmaLinux, `make deb` on Debian/Ubuntu.

**Upgrading from an older package:** no manual database steps are needed. On
first run, `hpc-eff` automatically renames the old `cpu_settings_log` table to
`hpc_eff_log` and adds the new GPU columns — all existing history is
preserved in place.

### After install (all distributions)

1. The package installs `/etc/hpc_eff/config.ini` from the example. If the file is missing, copy it first:
    ```bash
    sudo cp /etc/hpc_eff/config.ini.example /etc/hpc_eff/config.ini
    ```
2. Configure with your API key from [nowtricity](https://www.nowtricity.com/):
    ```bash
    sudo vi /etc/hpc_eff/config.ini
    ```
    Set `control_mode` under `[MODE]` to either `co2` or `temperature` (see [Regulation modes](#regulation-modes) below). NVIDIA GPU power regulation is included automatically in `temperature` mode.

3. Test the executable:
    ```bash
    sudo hpc-eff
    ```
4. Enable or disable the system cronjob using command-line switches:
    ```bash
    hpc-eff --enable
    hpc-eff --disable
    ```
    By default, the cronjob runs every 10 minutes and is installed at `/etc/cron.d/hpc-eff`.
    You can customize the path and interval:
    ```bash
    hpc-eff --enable --cron-path /custom/path --cron-interval 5
    ```
5. To read from the created database:
    ```bash
    sudo cp /var/lib/hpc_eff/history.db ~/history.db
    sqlite3 ~/history.db
    ```
    Inspect tables and data:
    ```
    .tables
    .schema hpc_eff_log
    SELECT * FROM hpc_eff_log LIMIT 10;
    ```

---

## Regulation modes

Three independent regulators can control system energy:
- **price/CO₂**: computes a rating (1–10) and caps the CPU max frequency.
- **temperature (CPU)**: hysteresis-based CPU max-frequency control.
- **GPU power**: reduces GPU power limit when temperature exceeds threshold.

The simplest way to choose CPU regulators is the `[MODE]` preset:

```ini
[MODE]
# temperature | co2
control_mode = co2
```

| Mode | Description | Use Case |
|------|-------------|----------|
| `co2` | Price/CO₂ regulator only | Classic energy governor for cost/carbon optimization |
| `temperature` | Temperature regulator only | Thermal management without energy considerations |

`control_mode` is the single switch for the whole node — there are no separate feature flags to set. It is required; an unset or unknown value aborts the run.

What each mode turns on under the hood:

- `control_mode = temperature` → CPU thermal control (`[CPU_THERMO]`) + NVIDIA GPU power regulation (`[GPU_POWER]`)
- `control_mode = co2` → CPU price/CO₂ frequency control only (rating 1–10 → max frequency)

The CPU is driven by either temperature or price/CO₂, never both. GPU power regulation rides along with `temperature` mode only (NVIDIA GPUs only; safely no-ops on nodes without them).

---

## Temperature source ("bring your own reader")

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
