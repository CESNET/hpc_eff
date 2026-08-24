# Configuration reference

Everything lives in a single INI file:

```
/etc/hpc_eff/config.ini
```

If that file does not exist, `hpc-eff` falls back to
`src/hpc_eff/config.ini.example` **relative to the current working
directory** — which is how you can run it straight from a git checkout, and
also why a run from an unexpected directory can appear to ignore your settings.

Sections are read lazily: a section that no active regulator needs is never
parsed. Which sections matter depends on `[MODE] control_mode`:

| Section | `co2` mode | `temperature` mode |
|---|:--:|:--:|
| `[SYSTEM]` | yes | yes |
| `[MODE]` | yes | yes |
| `[logging]` | yes | yes |
| `[CO2_API]` | yes | — |
| `[aggregation]` | yes | — |
| `[frequency_tables]` | yes | — |
| `[TEMPERATURE_SOURCE]` | — | yes |
| `[CPU_THERMO]` | — | yes |
| `[GPU_POWER]` | — | yes |

---

## `[MODE]`

The single user-facing switch. **Required** — an unset or unrecognised value
makes the run exit with `Config error: [MODE] control_mode must be one of:
temperature|co2` rather than silently doing nothing.

```ini
[MODE]
control_mode=co2
```

| Value | CPU regulator | GPU regulator |
|---|---|---|
| `co2` | price/CO₂ rating → max-frequency cap | off |
| `temperature` | hysteresis thermal control | NVIDIA power limiting, on |

CPU regulation is mutually exclusive by construction: one mode, one CPU
regulator.

---

## `[SYSTEM]`

```ini
[SYSTEM]
SCORENAME=SPEC2017
SCORE=3.8
POWERREADINGCMD=ipmitool dcmi power reading
DEBUG=yes
```

| Key | Default | Meaning |
|---|---|---|
| `SCORENAME` / `SCORE` | `unknown` / *(none)* | The node's benchmark name and score (e.g. its SPEC CPU2017 result), stamped onto every log row so you can later compare throttling impact against a node's rated performance. Set manually; never read back by the tool itself. |
| `POWERREADINGCMD` | *(empty)* | Shell command whose output is parsed for power draw. |
| `DEBUG` | `no` | `yes` prints the full evaluation trace to stdout. |

`POWERREADINGCMD` output must contain the four `ipmitool dcmi power reading`
lines; only `Instantaneous power reading` is stored (as `power_w`), logged
only — never acted on.

`DEBUG=yes` is safe to leave on; cron discards stdout regardless.

---

## `[CO2_API]` — carbon intensity backend

```ini
[CO2_API]
TYPE=nowtricity
```

`TYPE` selects the backend; the other backend's keys are ignored.

### `TYPE=nowtricity` (default)

| Key | Default | Meaning |
|---|---|---|
| `NOWTRICITY_API_KEY` | *(none)* | Sent as `X-Api-Key`. Get one at nowtricity.com. |
| `NOWTRICITY_USER_AGENT` | `HPC-Eff-Agent` | Sent as `User-Agent`. Use something that identifies your site. |
| `NOWTRICITY_BASE_URL` | `https://www.nowtricity.com/api` | |
| `NOWTRICITY_ZONE` | `czech-republic` | Grid zone slug. |

Two endpoints are called per run: `emissions-previous-24h/<zone>/` and
`current-emissions/<zone>/`. So a 10-minute interval means ~288 API calls per
node per day — check that against your plan's quota before a cluster-wide
rollout.

### `TYPE=wattnet`

| Key | Default | Meaning |
|---|---|---|
| `WATTNET_URL` | `https://api.wattnet.eu/v1/footprints` | |
| `WATTNET_API_KEY` | *(none)* | Sent as `Authorization: Bearer …`, omitted if unset or left as the placeholder. |
| `WATTNET_ZONE` | `CZ` | |
| `WATTNET_FOOTPRINT_TYPE` | `carbon` | |
| `WATTNET_SCOPE` | `operational` | |

The 24-hour window is computed automatically. Wattnet returns 15-minute
samples, which are averaged into 24 hourly values; the newest hourly average
doubles as the "current" value. **If fewer than 24 hourly values come back the
call fails** and the run falls back to the price rating.

---

## `[frequency_tables]` — rating → frequency map

```ini
[frequency_tables]
amd_epyc=2400,2000,1500
intel_xeon_gold=3000,2900,2800,2700,2600,2200
intel_e5=3000,2800,2700,2600,2400,2300
default=3000,2800,2700,2600,2400,2200
```

Values are **MHz, highest first**. The key is chosen by matching
`/proc/cpuinfo`:

| Key | Matches when the model name contains |
|---|---|
| `amd_epyc` | `EPYC` |
| `intel_e5` | `E5-` and `V3` |
| `intel_xeon_gold` | `GOLD` |
| `default` | everything else |

Selection is `index = round((rating - 1) / 9 × (len - 1))` over the
descending-sorted list: rating 1 takes the first entry, rating 10 the last,
the rest are spread evenly. The list length is your granularity — see
[deployment.md §7](deployment.md#7-tune-the-frequency-table).

If the section or the key is missing entirely the built-in fallback
`3000,2800,2700,2600,2400,2200` applies, which may be nonsense on your CPU.
Set `default` explicitly.

---

## `[aggregation]` — combining price and CO₂

```ini
[aggregation]
rating_type=average
weight_price=0.6
weight_co2=0.4
```

| Key | Default | Meaning |
|---|---|---|
| `rating_type` | `price` | `price` \| `average` \| `max` — see [regulation-modes.md](regulation-modes.md#choosing-rating_type) |
| `weight_price` | `0.6` | Used by `average` only, normalised against `weight_co2` |
| `weight_co2` | `0.4` | Used by `average` only |

An unknown `rating_type` logs a warning and falls back to the price rating.

Fallback chain when a signal is missing: CO₂ unavailable → price rating; price
unavailable → CO₂ rating; both unavailable → **neutral 5**. The node keeps
regulating rather than freezing at its last cap.

Rationale for the default weights: [regulation-modes.md](regulation-modes.md#why-price-is-weighted-higher-than-carbon).

---

## `[logging]`

```ini
[logging]
db_path=/var/lib/hpc_eff/history.db
state_json_path=/var/lib/hpc_eff/state.json
history_length=1000
log_level=INFO
```

| Key | Default | Meaning |
|---|---|---|
| `db_path` | `history.db` | SQLite file. Parent directory is created if needed; WAL mode is enabled. |
| `state_json_path` | `/var/lib/hpc_eff/state.json` | JSON state file, rewritten each run, chmod 644. |
| `history_length` | `10` | How many past entries `state.json` keeps. |
| `log_level` | `INFO` | Python level for the `hpc_eff` logger (stderr). |

`history_length` only bounds the JSON file, not the database — see
[monitoring.md](monitoring.md#the-database) for growth/pruning.

`log_level` affects stderr only, which cron discards.

---

## `[TEMPERATURE_SOURCE]` — pluggable temperature reading

Used only in `temperature` mode (by both the CPU thermal regulator and the GPU
power regulator — they share one reading).

```ini
[TEMPERATURE_SOURCE]
TYPE=ipmi
IPMI_SENSOR_NAME=INLET_AIR_TEMP
```

| `TYPE` | Keys | Behaviour |
|---|---|---|
| `ipmi` | `IPMI_SENSOR_NAME` | Runs `ipmitool sensor reading "<name>"` and takes the first number in the output. |
| `http_api` | `HTTP_URL`, `HTTP_JSON_PATH` *(optional)* | GETs the URL (5 s timeout). Tries a bare number, then JSON, then any number in the body. |
| `custom` | `MODULE`, `FUNCTION` *(default `read`)* | Loads your code and calls it. |

HTTP example — for `{"temperature": {"value": 25.5}}`:

```ini
TYPE=http_api
HTTP_URL=http://192.168.1.100/api/greendigit/data
HTTP_JSON_PATH=temperature.value
```

Without `HTTP_JSON_PATH` the reader tries the top-level keys `temperature`,
`temp`, `value`, `data` before falling back to a regex for the first number in
the response.

Custom reader — `MODULE` is a path to a `.py` file or an importable dotted
module name; `FUNCTION` (default `read`) must return Celsius as a number, or
`None`:

```ini
TYPE=custom
MODULE=/opt/mysensors/my_reader.py
FUNCTION=read
```

Every source swallows its own exceptions and returns `None` on failure, which
makes the whole thermal regulation a no-op for that cycle. A typo in a sensor
name therefore looks like "nothing happens", not like an error — check with
`ipmitool sensor reading "<name>"` by hand.

---

## `[CPU_THERMO]` — thermal CPU control

```ini
[CPU_THERMO]
MID_LIMIT=29
HIGH_LIMIT=32
HIGH_FREQUENCY=3.10GHz
MID_FREQUENCY=2.30GHz
LOW_FREQUENCY=1.50GHz
#SLACK_URL=
```

| Key | Meaning |
|---|---|
| `MID_LIMIT` / `HIGH_LIMIT` | Band edges in °C |
| `HIGH_/MID_/LOW_FREQUENCY` | Target max frequency per band. Accepts `3.10GHz`, `2300MHz`, `2300000KHz`, or a bare number (MHz below 10000, else kHz). |
| `SLACK_URL` | Optional incoming webhook, posted to only when the frequency actually changes. |

The default limits (29/32 °C) are **inlet air** temperatures, not core
temperatures. Aim them at whatever your sensor actually measures.

If any of the five keys is missing the regulator logs a debug line and skips —
silently, as far as cron is concerned.

Band logic and hysteresis: [regulation-modes.md](regulation-modes.md#temperature-mode).

---

## `[GPU_POWER]` — NVIDIA power limiting

Active in `temperature` mode only, and a no-op on nodes without NVIDIA GPUs.

```ini
[GPU_POWER]
MID_LIMIT=70
HIGH_LIMIT=80
HIGH_POWER=100%
MID_POWER=70%
LOW_POWER=40%
# SLACK_URL=
```

| Key | Default | Meaning |
|---|---|---|
| `MID_LIMIT` | `70` | °C — start reducing power above this |
| `HIGH_LIMIT` | `80` | °C — aggressive reduction above this |
| `HIGH_/MID_/LOW_POWER` | `100%` / `70%` / `40%` | Absolute watts (`250`) or a percentage of the GPU's max limit (`70%`) |

Percentages resolve against `nvidia-smi --query-gpu=power.max_limit`, falling
back to the current limit, and finally to 300 W. **All GPUs in the node get the
same limit**, derived from the one ambient temperature — this is not per-GPU
regulation, and it does not read GPU die temperature.

The temperature comes from `[TEMPERATURE_SOURCE]`, the same reading the CPU
thermal regulator uses. Note that its defaults (29/32 °C) are inlet-air scale
while these defaults (70/80 °C) are die-temperature scale — if you enable both
against one inlet sensor, the GPU thresholds will never trigger. Set both pairs
against the same sensor's real range.
