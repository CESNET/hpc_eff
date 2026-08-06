# ThrottlePoint

**Energy Optimization Governor** for HPC systems.  
Dynamically adjusts CPU frequencies and GPU power based on power, electricity price, CO₂ intensity, and temperature. Which signals drive the decision is fully configurable, and you can plug in your own temperature/data source.

All the functionality and code logic located in `src/hpc_eff` stem from https://gitlab.cesnet.cz/dexter/hpc_eff.

## ThrottlePoint use cases
* Driver: carbon intensity of electricity
  * Primary GreenDIGITscenario
  * Lowering carbon impact
* Driver: electricity cost or consumption profile
  * Lowering operational costs
* Driver: datacenter temperature
  * Optimize datacenter usage
  * Continuity of services
* Driver: power-grid or local heating signals
  * Lowering operational costs, carbon impact

<table>
  <tr>
    <td>
      <a href="docs/images/ThrottlePoint-usecases-1.png">
        <img src="docs/images/ThrottlePoint-usecases-1.png" alt="ThrottlePoint Use Case 1" width="200"/>
      </a>
    </td>
    <td>
      <a href="docs/images/ThrottlePoint-usecases-2.png">
        <img src="docs/images/ThrottlePoint-usecases-2.png" alt="ThrottlePoint Use Case 2" width="200"/>
      </a>
    </td>
    <td>
      <a href="docs/images/ThrottlePoint-usecases-3.png">
        <img src="docs/images/ThrottlePoint-usecases-3.png" alt="ThrottlePoint Use Case 3" width="200"/>
      </a>
    </td>
    <td>
      <a href="docs/images/ThrottlePoint-usecases-4.png">
        <img src="docs/images/ThrottlePoint-usecases-4.png" alt="ThrottlePoint Use Case 4" width="200"/>
      </a>
    </td>
  </tr>
</table>

---
## Overview

ThrottlePoint is designed to be run periodically (e.g., via `cron` every few minutes) under root.  
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
git clone git@github.com:CESNET/throttlepoint.git
cd throttlepoint
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

### Combined price + CO₂ rating

In `co2` mode two independent ratings (1–10) are computed each cycle:

- **Price rating** — the current spot price (spotovaelektrina.cz) classified against a full year of monthly averages via `classify_price_by_median`.
- **CO₂ rating** — the current grid carbon intensity (Nowtricity) graded as a percentile within the last 24 hours of values.

How they are merged into the final rating that selects the CPU max frequency is controlled by the `[aggregation]` section:

```ini
[aggregation]
# price | average | max
rating_type = average
weight_price = 0.6
weight_co2 = 0.4
```

| `rating_type` | Behaviour |
|---------------|-----------|
| `price` | Price rating only (legacy behaviour; also used when the section is absent) |
| `average` | Weighted average of both ratings (price + CO₂), rounded and clamped to 1–10 |
| `max` | The worse (higher) of the two — "throttle if *either* is expensive or dirty" |

If the CO₂ API is unavailable, `average` and `max` transparently fall back to the price rating so the node keeps regulating. All three values (`rating_price`, `rating_co2`, and the combined `rating`) are written to the database and state JSON, so weights can be tuned against real history.

**Why is price weighted higher than CO₂?** The two ratings are computed against very different baselines. The price rating is measured against a *year* of monthly averages — it is a stable, absolute signal where a 9 genuinely means "expensive compared to the whole year". The CO₂ grade is only a percentile within the *last 24 hours*, so it sweeps the full 1–10 range every single day: even on a uniformly clean day, the cleanest hour grades 1 and the dirtiest grades 10. Giving CO₂ an equal or higher weight would let this day-relative volatility dominate the frequency cap. The 0.6/0.4 split keeps the long-term price signal in charge while letting intraday carbon intensity nudge the cap toward cleaner hours. (In the Czech grid the two correlate anyway — both spike when fossil plants set the marginal price — so the CO₂ term mostly acts as a fine-tuning signal.)

### Price data source (spotovaelektrina.cz)

The price rating uses two endpoints of [spotovaelektrina.cz](https://spotovaelektrina.cz), which republishes Czech OTE spot market prices:

- **Current price** — `https://spotovaelektrina.cz/api/v1/price/get-actual-price-czk`, a JSON-free endpoint returning the current hour's price as a plain integer (CZK/MWh).
- **Historical baseline** — [`https://spotovaelektrina.cz/historicke-ceny/<year>/1`](https://spotovaelektrina.cz/historicke-ceny), scraped from HTML (there is no public API for history). Each page lists one table row per month with the monthly average as the first `⌀ … Kč` cell. The whole calendar year is present on every page regardless of the `<month>` path segment.

`get_averages_year()` builds the baseline from the **current date**: it fetches the current *and* previous year's page and keeps the most recent 12 monthly averages, so the classification window is always the trailing ~year — including in January, when the current-year page alone would contain only a few weeks of data.

Because the history is scraped, a site redesign could silently break parsing. The parser therefore raises a clear error if fewer than 6 monthly values could be extracted; the controller then logs it and the cycle falls back to the CO₂ rating (or the neutral rating 5 if that is also unavailable) rather than regulating against a corrupt baseline.

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
