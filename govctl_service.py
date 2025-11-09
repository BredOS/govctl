#!/usr/bin/env python3

import json
import os
import time
import logging
import signal
import subprocess
from pathlib import Path
import logging.handlers

CONFIG_PATH = "/etc/govctl/config.json"
LOG_TAG = "govctl"
RAPLCTL_PATH = "/usr/bin/raplctl"

VALID_CPU_GOVS = ["powersave", "conservative", "performance"]
VALID_DEVFREQ_GOVS = ["powersave", "performance"]

isi = False  # Is Intel
isa = False  # Is AMD

isx = os.uname().machine == "x86_64"  # Is x86_64
if isx:
    try:
        with open("/proc/cpuinfo", "r") as f:
            isi = "GenuineIntel" in f.read()
    except Exception:
        pass  # Ignore errors if /proc/cpuinfo is not available

CPU_GOVERNOR_PATH = "/sys/devices/system/cpu/cpu*/cpufreq/scaling_governor"
DEVFREQ_GOVERNOR_PATH = "/sys/class/devfreq/*/governor"
BATTERY_PATH = "/sys/class/power_supply/"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.handlers.SysLogHandler(
            address="/dev/log", facility=logging.handlers.SysLogHandler.LOG_DAEMON
        )
    ],
)

# Globals
current_config = {}
force_show = True
powersave = False


def load_config() -> None:
    global current_config
    try:
        with open(CONFIG_PATH, "r") as f:
            current_config = json.load(f)
        logging.info("Configuration reloaded")
    except Exception as e:
        logging.error(f"Failed to load config: {e}")


def run_raplctl(governor: str) -> None:
    if not (isi and Path(RAPLCTL_PATH).exists()):
        return

    command = []
    if governor == "performance":
        command = [RAPLCTL_PATH, "-w", "long=900,short=900,long_time=300"]
    elif governor == "powersave":
        command = [RAPLCTL_PATH, "-w", "long=8,short=12,long_time=20"]
    elif governor == "conservative_x86":
        command = [RAPLCTL_PATH, "-w", "long=15,short=20,long_time=20"]

    if not command:
        return

    try:
        result = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
        )
        logging.info(f"Successfully ran raplctl for {governor} mode.")
        if result.stdout:
            logging.info(f"raplctl output: {result.stdout.strip()}")
    except subprocess.CalledProcessError as e:
        logging.error(f"Failed to run raplctl: {e}")
        if e.stderr:
            logging.error(f"raplctl error: {e.stderr.strip()}")


def set_governor(governor: str) -> None:
    global force_show
    altered = False
    if governor not in VALID_CPU_GOVS:
        logging.error(f"Invalid CPU governor: {governor}")

    rapl_mode = governor
    if isx and governor == "conservative":
        logging.warning(
            'Applying "powersave" governor with custom power limits for conservative mode.'
        )
        rapl_mode = "conservative_x86"
        governor = "powersave"

    # Set raplctl limits before changing governor
    run_raplctl(rapl_mode)

    for cpu_path in Path("/sys/devices/system/cpu/").glob(
        "cpu*/cpufreq/scaling_governor"
    ):
        if cpu_path.read_text().strip() != governor:
            try:
                cpu_path.write_text(governor)
                if cpu_path.read_text().strip() != governor:
                    raise Exception
                logging.info(f"Set {cpu_path} to {governor}")
                altered = True
            except Exception as e:
                logging.error(f"Failed to set {cpu_path}: {e}")

    devfreq_gov = "powersave" if governor == "conservative" else governor

    for devfreq_path in Path("/sys/class/devfreq/").glob("*/governor"):
        if devfreq_path.read_text().strip() != devfreq_gov:
            try:
                devfreq_path.write_text(devfreq_gov)
                if devfreq_path.read_text().strip() != devfreq_gov:
                    raise Exception
                logging.info(f"Set {devfreq_path} to {devfreq_gov}")
                altered = True
            except Exception as e:
                logging.error(f"Failed to set {devfreq_path}: {e}")

    if altered or force_show:
        if force_show:
            force_show = False
            time.sleep(0.5)
        logging.info(f'Applied governor "{governor}"')


def fetch_prop(dev: Path, attr: str) -> str:
    dev_path = dev / attr
    if not dev_path.exists():
        return ""

    return dev_path.read_text().strip()


def status() -> int:
    perc_min = 100

    for device in Path(BATTERY_PATH).iterdir():
        if ("hidpp" not in str(device)) and not (
            str(device).startswith(BATTERY_PATH + "hid-")
        ):
            try:
                energy_now = fetch_prop(device, "energy_now")
                energy_full = fetch_prop(device, "energy_full")

                charge_now = fetch_prop(device, "charge_now")

                charge_full = fetch_prop(device, "charge_full")

                online = fetch_prop(device, "online")

                if online and int(online):
                    return 100
                elif energy_full and int(energy_full):
                    perc_min = min(
                        (1 - ((int(energy_full) - int(energy_now)) / int(energy_full)))
                        * 100,
                        perc_min,
                    )
                elif charge_full and int(charge_full):
                    perc_min = min(
                        (1 - ((int(charge_full) - int(charge_now)) / int(charge_full)))
                        * 100,
                        perc_min,
                    )
            except Exception as e:
                logging.error(f"Error parsing device {device}: {e}")

    return int(perc_min)


def reload(signum, frame) -> None:
    global force_show
    load_config()
    force_show = True


def delay() -> None:
    period = 5 if powersave else 20
    for _ in range(period):
        time.sleep(1)
        if force_show:
            return


def main():
    logging.info("Starting GovCtl")
    global force_show, powersave

    signal.signal(signal.SIGHUP, reload)
    load_config()

    while True:
        if not current_config:
            logging.warning("Config could not be loaded, retrying in 10s.")
            time.sleep(10)
            continue

        desired_governor = current_config.get("governor", "performance")
        battery_governor = current_config.get("governor_battery", "conservative")
        detect_battery = current_config.get("detect_battery_state", False)
        powersave_point = max(min(current_config.get("powersave_point", 20), 80), 0)

        st = status() if detect_battery else 100

        if powersave:
            if st < (powersave_point + 10):
                set_governor("powersave")
            else:
                logging.info("Adequate power detected, switching to normal mode.")
                powersave = False
                set_governor(desired_governor if st == 100 else battery_governor)
            delay()
        else:
            if st > powersave_point:
                set_governor(desired_governor if st == 100 else battery_governor)
            else:
                logging.info("Low battery detected, switching to powersave.")
                powersave = True
                set_governor("powersave")
            delay()

    logging.warning("Exiting GovCtl")


if __name__ == "__main__":
    main()
