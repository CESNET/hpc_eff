# Cluster rollout

Going from one verified node to many, then upgrading and uninstalling. Verify
a single node first with [deployment.md](deployment.md); nothing here helps if
the pilot node is not already working.

---

## Rolling out

Nothing in the design is cluster-aware. Each node decides for itself, with no
coordination, no shared state, and no head node. Rollout is therefore only
"install the package and drop in a config":

1. **Build once per architecture.** The RPM is `noarch`; the DEB builds as
   `amd64` and needs a matching build host for other architectures.
2. **Distribute** the `.rpm` or `.deb` to a local repo, or push the file
   directly.
3. **Ship one config per hardware group.** In `co2` mode `[frequency_tables]`
   is the only hardware-specific part; the API keys and aggregation weights
   are identical everywhere. In `temperature` mode it is `[CPU_THERMO]` and
   `[GPU_POWER]`, and the grouping is by *sensor* as much as by CPU model —
   nodes in different rooms or airflow positions read different temperatures
   and need different limits even with identical CPUs.
4. **Enable cron last**, after a manual `sudo hpc-eff` on one node of each
   group has been verified. On Debian, remember the package already enabled it.
5. **Stagger the interval** across large groups in `co2` mode if you are
   worried about hammering the upstream APIs — `--cron-interval 10` everywhere
   means hundreds of nodes fetching the same price in the same second. There
   is no built-in jitter; edit `/etc/cron.d/hpc-eff` per group to different
   offsets (`3,13,23,33,43,53` instead of `*/10`). `temperature` mode calls no
   external API, so this does not apply — unless your source is one shared
   HTTP endpoint, in which case it applies just as much.

`/etc/hpc_eff/config.ini` is a proper conffile in both packages
(`%config(noreplace)` and dpkg conffile), so a package upgrade does not
overwrite the config you deployed.

---

## Upgrading

```bash
sudo dnf install -y ~/rpmbuild/RPMS/noarch/hpc_eff-*.noarch.rpm   # or: make reinstall
sudo dpkg -i ../hpc-eff_*.deb
```

No manual database migration is needed. On start, `hpc-eff` renames a legacy
`cpu_settings_log` table to `hpc_eff_log` and adds any columns the schema has
gained since the database was created. Existing history is preserved in place.

---

## Uninstalling

```bash
sudo hpc-eff --disable       # do this first, see the warning below
sudo rpm -e hpc_eff          # or: make uninstall
sudo dpkg --purge hpc-eff    # --purge also removes the config
```

> **Warning:** removing the package does not restore the CPU frequency. The
> last cap applied stays in `scaling_max_freq` until something resets it:
>
> ```bash
> sudo cpupower frequency-set -u $(cat /sys/devices/system/cpu/cpu0/cpufreq/cpuinfo_max_freq)
> # or: sudo cpufreq-set --max $(cat .../cpuinfo_max_freq)
> ```
>
> The same applies to the GPU power limit in `temperature` mode — it stays
> wherever the last run left it:
>
> ```bash
> sudo nvidia-smi -pl $(nvidia-smi --query-gpu=power.max_limit --format=csv,noheader,nounits | head -1)
> ```
>
> A reboot also clears both.

---

## What to check after the first week

In `co2` mode:

```bash
sudo sqlite3 /var/lib/hpc_eff/history.db "
  SELECT date(timestamp) AS day,
         COUNT(*)          AS runs,
         SUM(rating_co2 IS NULL) AS co2_failures,
         MIN(freq_max), MAX(freq_max), AVG(rating)
  FROM hpc_eff_log GROUP BY day ORDER BY day DESC LIMIT 7;"
```

| Look for | Healthy | Wrong |
|---|---|---|
| `runs` per day | 144 at a 10-minute interval | far fewer → cron is not firing |
| `co2_failures` | 0, or occasional | every row → API key or egress broken |
| `AVG(rating)` | somewhere near 5 | pinned at 5 → both signals are failing |
| `freq_max` spread | several distinct values | one value → the table has too few entries, or the rating never moves |

In `temperature` mode:

```bash
sudo sqlite3 /var/lib/hpc_eff/history.db "
  SELECT date(timestamp) AS day,
         COUNT(*)          AS runs,
         SUM(temperature IS NULL) AS temp_failures,
         MIN(temperature), MAX(temperature),
         COUNT(DISTINCT freq_max) AS distinct_caps
  FROM hpc_eff_log GROUP BY day ORDER BY day DESC LIMIT 7;"
```

| Look for | Healthy | Wrong |
|---|---|---|
| `runs` per day | 144 at a 10-minute interval | far fewer → cron is not firing |
| `temp_failures` | 0 | any → the sensor is unreadable and no cap was applied; check `action_temp` in `state.json` |
| temperature range | a plausible daily swing | flat or absurd → wrong sensor name, check `ipmitool sensor list` |
| `distinct_caps` | 1 in a stable room, 2–3 if it warms up | always 3 → your limits sit below this sensor's normal range, see [deployment.md](deployment.md#temperature-mode-the-thermal-bands) |

A node that never leaves `HIGH_FREQUENCY` is not necessarily broken: it means
the room stayed below `MID_LIMIT`, which is the intended steady state. It
matters only if you expected intervention and never got it.

More queries — energy saved, hours spent at each cap — in
[monitoring.md](monitoring.md).

---

## See also

- [install.md](install.md): prerequisites and building the packages
- [deployment.md](deployment.md): configuring and verifying a single node
- [monitoring.md](monitoring.md): database schema, `state.json`, queries
- [troubleshooting.md](troubleshooting.md): when a step above fails
