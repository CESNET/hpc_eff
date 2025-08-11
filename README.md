# hpc_eff
This tool dynamically optimizes energy consumption on HPC systems by
adjusting the CPU frequency according to the current carbon intensity (CI)
of electricity production.

Designed to be run periodically (e.g., via cron every 5 minutes under root),
it applies a hardcoded policy that limits CPU frequency in proportion to
real-time carbon intensity data obtained from the GreenDIGIT CI database.
The frequency regulator outputs a standardized score (0–100), representing
the percentage limit relative to the maximum CPU frequency.

## Installation

1. `git clone git@github.com:CESNET/hpc_eff.git`

2. `sudo dnf install ipmitool`

3. `make`

Add your API key to /etc/hpc_eff/config.ini
