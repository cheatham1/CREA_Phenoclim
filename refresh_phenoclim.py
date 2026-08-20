#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
refresh_phenoclim.py
====================
One entry point for the *recurring* refresh that keeps the dashboard current.

What one run does
-----------------
1. build_phenoclim_data.py fetches the full export from the CREA API,
2. cleans it and drops impossible coordinates,
3. assigns each nom_zone to a massif (cached — only NEW zones are geocoded),
   splitting the Alps into Alpes du Nord / Alpes du Sud,
4. aggregates and writes phenoclim_data.json, which the dashboard fetches at
   load time.

Because the zone->region lookup is cached in zone_regions.csv, the recurring
run stays fast and does the heavy geocoding only when a genuinely new
monitoring zone appears.

Usage
-----
    python3 refresh_phenoclim.py                 # normal recurring run (hits API)
    python3 refresh_phenoclim.py --raw FILE      # rebuild from a cached export
    python3 refresh_phenoclim.py --refresh-regions   # force full re-geocode
    python3 refresh_phenoclim.py --cron          # print a crontab line and exit

Scheduling
----------
--cron prints a ready-to-paste crontab line (weekly, Monday 03:15). It does not
install anything; copy it into `crontab -e` yourself. Phénoclim observations
arrive seasonally, so daily is overkill — weekly (or even monthly outside
spring/autumn) is plenty.
"""

import os
import sys
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
BUILD = os.path.join(HERE, "build_phenoclim_data.py")

# Reference files for exact region assignment. Override via environment if you
# keep them elsewhere; defaults assume they sit next to this script.
os.environ.setdefault("PHENO_COMMUNES", os.path.join(HERE, "a-com2022-topo-2154.json"))
os.environ.setdefault("PHENO_MASSIF",   os.path.join(HERE, "diffusion-zonages-massifs-cog2021.xls"))


def print_cron():
    py = sys.executable or "python3"
    line = (f"15 3 * * 1 cd {HERE} && {py} build_phenoclim_data.py "
            f">> {os.path.join(HERE, 'refresh.log')} 2>&1")
    print("# Phénoclim weekly refresh — add to `crontab -e`:")
    print(line)
    print("\n# For a monthly refresh instead (1st of the month, 03:15):")
    print(line.replace("* * 1", "1 * *"))


def main():
    if "--cron" in sys.argv:
        print_cron()
        return
    # Pass through the flags build_phenoclim_data.py understands.
    passthrough = [a for a in sys.argv[1:]
                   if a in ("--refresh-regions", "--raw")
                   or (sys.argv[sys.argv.index(a) - 1] == "--raw"
                       if a in sys.argv else False)]
    # simpler: just forward everything except our own --cron
    passthrough = [a for a in sys.argv[1:] if a != "--cron"]
    cmd = [sys.executable or "python3", BUILD] + passthrough
    print("running:", " ".join(cmd))
    raise SystemExit(subprocess.call(cmd, cwd=HERE))


if __name__ == "__main__":
    main()
