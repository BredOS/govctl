#!/usr/bin/env python3

import json, os, time, logging, signal, subprocess
import shutil, re
from pathlib import Path
import logging.handlers

CONFIG_PATH = "/etc/govctl/config.json"
LOG_TAG = "govctl"
RAPLCTL_PATH = "/usr/bin/raplctl"
RYZENADJ_PATH = "/usr/bin/ryzenadj"

VALID_CPU_GOVS = ["powersave", "conservative", "performance"]
VALID_DEVFREQ_GOVS = ["powersave", "performance"]

# Intel Constants
INTEL_MSR_PKG_POWER_LIMIT = 0x610
INTEL_PACKAGE_RAPL_LIMIT_0_0_0_MCHBAR_PCU = 0x59A0
INTEL_PL1_ENABLE_BITS_LOW = 0x00008000
INTEL_PL2_ENABLE_BITS_HIGH = 0x00008000
# Combine bits: PL1 is low word, PL2 is high word (shifted 32)
INTEL_PL1_PL2_ENABLE_BITS = INTEL_PL1_ENABLE_BITS_LOW | (
    INTEL_PL2_ENABLE_BITS_HIGH << 32
)

PL_UNCAP_REQUIRED_TOOLS = ["devmem2", "rdmsr", "wrmsr", "turbostat", "setpci"]
PL_UNCAP_MISSING = [tool for tool in PL_UNCAP_REQUIRED_TOOLS if not shutil.which(tool)]

isi = False  # Is Intel
isa = False  # Is AMD

isx = os.uname().machine == "x86_64"  # Is x86_64
if isx:
    try:
        with open("/proc/cpuinfo", "r") as f:
            data = f.read()
            isi = "GenuineIntel" in data
            isa = "AuthenticAMD" in data
    except Exception:
        pass  # Ignore errors if /proc/cpuinfo is not available

    # Check if power-profiles-daemon is running
    try:
        result = subprocess.run(
            ["systemctl", "is-active", "--quiet", "power-profiles-daemon"], check=False
        )
        if result.returncode == 0:
            print(
                "Error: Conflicting with power-profiles-daemon! Exiting..",
                file=sys.stderr,
            )
            sys.exit(1)
    except:
        pass

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
applied_tdp = None
last_config_mtime = 0


def load_config() -> None:
    global current_config, last_config_mtime, force_show, applied_tdp
    try:
        config_path = Path(CONFIG_PATH)
        if not config_path.exists():
            return

        # Check modification time
        current_mtime = config_path.stat().st_mtime

        # Only reload if the time is different from the last load
        if current_mtime != last_config_mtime:
            with open(CONFIG_PATH, "r") as f:
                current_config = json.load(f)
            last_config_mtime = current_mtime

            # Force re-application of settings
            force_show = True
            # Reset applied_tdp to ensure raplctl/ryzenadj run again
            applied_tdp = None

            logging.info("Configuration reloaded due to file change")
    except Exception as e:
        logging.error(f"Failed to load config: {e}")


def run_raplctl(governor: str, tdps: dict) -> None:
    global applied_tdp
    if not (isi and Path(RAPLCTL_PATH).exists()):
        return

    if applied_tdp == governor:
        return

    command = []
    if governor == "conservative_x86":
        governor = "conservative"

    command = [
        RAPLCTL_PATH,
        "-w",
        f"long={int(tdps[governor])},short={int(min(tdps[governor] * (1 + (tdps['boost']/100)), 900))},long_time={300 if governor == 'performance' else 20}",
    ]

    try:
        result = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
        )
        logging.info(f"Successfully ran raplctl for {governor} mode.")
        applied_tdp = governor
        if result.stdout:
            logging.info(f"raplctl output: {result.stdout.strip()}")
    except subprocess.CalledProcessError as e:
        logging.error(f"Failed to run raplctl: {e}")
        if e.stderr:
            logging.error(f"raplctl error: {e.stderr.strip()}")


def run_ryzenadj(governor: str, tdps: dict) -> None:
    global applied_tdp
    if not (isa and Path(RYZENADJ_PATH).exists()):
        return

    if applied_tdp == governor:
        return

    command = []
    if governor == "conservative_x86":
        governor = "conservative"

    command = [
        RYZENADJ_PATH,
        f"--stapm-limit={int(tdps[governor] * 1000)}",
        f"--slow-limit={int(tdps[governor] * 1000)}",
        f'--fast-limit={int(min(tdps[governor] * (1 + (tdps["boost"]/100)), 900)) * 100}',
    ]

    try:
        result = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
        )
        logging.info(f"Successfully ran ryzenadj for {governor} mode.")
        applied_tdp = governor
        if result.stdout:
            logging.info(f"ryzenadj output: {result.stdout.strip()}")
    except subprocess.CalledProcessError as e:
        logging.error(f"Failed to run ryzenadj: {e}")
        if e.stderr:
            logging.error(f"ryzenadj error: {e.stderr.strip()}")


def set_governor(governor: str, tdps: dict) -> None:
    global force_show
    altered = False
    if governor not in VALID_CPU_GOVS:
        logging.error(f"Invalid CPU governor: {governor}")

    effective_governor = governor
    if isx and governor == "conservative":
        governor = "powersave"

    # Set tdp before governor
    run_raplctl(effective_governor, tdps)
    run_ryzenadj(effective_governor, tdps)

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
        logging.info(f'Applied governor "{effective_governor}"')


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
    global last_config_mtime
    last_config_mtime = 0


def delay() -> None:
    period = 5 if powersave else 20
    for _ in range(period):
        time.sleep(1)
        load_config()  # Check for config changes every second
        if force_show:
            return


def read_phys_mem_word(address: int) -> int:
    cmd = ["devmem2", hex(address), "w"]
    try:
        output = subprocess.check_output(cmd, stderr=subprocess.STDOUT).decode()
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"devmem2 failed: {e.output.decode()}") from e

    match = re.search(r"Value at address.*: (0x[0-9A-Fa-f]+)", output)
    if not match:
        raise ValueError("Could not parse devmem2 output")

    return int(match.group(1), 16)


def write_phys_mem_word(address, value):
    cmd = ["devmem2", hex(address), "w", hex(value)]
    try:
        subprocess.check_output(cmd, stderr=subprocess.STDOUT)
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"devmem2 write failed: {e.output.decode()}") from e


def read_msr(address):
    cmd = ["rdmsr", "--hexadecimal", "--zero-pad", "--c-language", hex(address)]
    try:
        output = subprocess.check_output(cmd, stderr=subprocess.STDOUT).decode().strip()
        return int(output, 16)
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"rdmsr failed: {e.output.decode()}") from e


def write_msr(address, value):
    """Writes a value to an MSR using wrmsr."""
    cmd = ["wrmsr", hex(address), hex(value)]
    try:
        subprocess.check_output(cmd, stderr=subprocess.STDOUT)
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"wrmsr failed: {e.output.decode()}") from e


def enable_msr_limits():
    msr_val = read_msr(INTEL_MSR_PKG_POWER_LIMIT)

    if (msr_val & INTEL_PL1_PL2_ENABLE_BITS) != INTEL_PL1_PL2_ENABLE_BITS:
        print("Enabling PL1 and PL2 bits in MSR...")
        new_val = msr_val | INTEL_PL1_PL2_ENABLE_BITS
        write_msr(INTEL_MSR_PKG_POWER_LIMIT, new_val)


def get_mchbar_address():
    cmd = ["setpci", "-s", "00:00.0", "48.l"]
    output = subprocess.check_output(cmd).decode().strip()
    mchbar = int(output, 16)

    # Check enable bit (bit 0)
    if not (mchbar & 1):
        raise RuntimeError("MCHBAR is not enabled.")

    # Clear enable bit to get physical address
    return mchbar & ~1


def disable_mmio_limits() -> None:
    mchbar = get_mchbar_address()
    rapl_addr = mchbar + INTEL_PACKAGE_RAPL_LIMIT_0_0_0_MCHBAR_PCU

    # Read current 64-bit value (split into two 32-bit reads)
    low = read_phys_mem_word(rapl_addr)
    high = read_phys_mem_word(rapl_addr + 4)

    if (not low) and (not high):
        return

    print(f"Current MMIO RAPL Limit: 0x{high:08x}:0x{low:08x}")

    # Check lock bit (bit 31 of high word)
    is_locked = (high & 0x80000000) != 0

    if is_locked:
        pl1_active = low & INTEL_PL1_ENABLE_BITS_LOW
        pl2_active = high & INTEL_PL2_ENABLE_BITS_HIGH

        if pl1_active or pl2_active:
            print("Warning: MMIO is locked and limits are enabled. Cannot override.")
            raise RuntimeError
    else:
        print("MMIO not locked. Zeroing out register to disable MMIO limits.")
        write_phys_mem_word(rapl_addr, 0x00000000)
        write_phys_mem_word(rapl_addr + 4, 0x00000000)


def try_uncap_power() -> None:
    if PL_UNCAP_MISSING:
        logging.warning("Binaries missing for power limit uncap!")
        logging.warning("---------------------------------------")
        for i in PL_UNCAP_MISSING:
            logging.warning(f" - {i}")
        logging.warning("---------------------------------------")
        return
    else:
        logging.info("PL uncap will be attempted.")
    try:
        enable_msr_limits()
        disable_mmio_limits()
        logging.info("PL uncap complete.")
    except:
        logging.warning("Failed to uncap PL")


def main():
    logging.info("Starting GovCtl")
    global force_show, powersave

    signal.signal(signal.SIGHUP, reload)
    load_config()

    if isi:
        try_uncap_power()

    while True:
        # Also check config at the start of every loop
        load_config()

        if not current_config:
            logging.warning("Config could not be loaded, retrying in 10s.")
            time.sleep(10)
            continue

        desired_governor = current_config.get("governor", "performance")
        battery_governor = current_config.get("governor_battery", "conservative")
        detect_battery = current_config.get("detect_battery_state", False)
        powersave_point = max(min(current_config.get("powersave_point", 20), 80), 0)

        tdps = current_config.get("tdp", None)
        default_tdps = {
            "boost": 50,
            "performance": 900,
            "conservative": 13,
            "powersave": 8,
        }

        if tdps is None:
            tdps = default_tdps
        else:
            validated_tdps = {}
            for key, default_value in default_tdps.items():
                value = tdps.get(key, default_value)
                try:
                    int_value = int(value)
                    if int_value <= 0:
                        raise ValueError
                    validated_tdps[key] = int_value
                except (ValueError, TypeError):
                    validated_tdps[key] = default_value
            tdps = validated_tdps

        st = status() if detect_battery else 100

        if powersave:
            if st < (powersave_point + 10):
                set_governor("powersave", tdps)
            else:
                logging.info("Adequate power detected, switching to normal mode.")
                powersave = False
                set_governor(
                    (desired_governor if st == 100 else battery_governor), tdps
                )
            delay()
        else:
            if st > powersave_point:
                set_governor(
                    (desired_governor if st == 100 else battery_governor), tdps
                )
            else:
                logging.info("Low battery detected, switching to powersave.")
                powersave = True
                set_governor("powersave", tdps)
            delay()

    logging.warning("Exiting GovCtl")


if __name__ == "__main__":
    main()
