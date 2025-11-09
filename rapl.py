#!/usr/bin/env python3
import argparse
import os
import subprocess
from collections import defaultdict

RAPL_PATH = "/sys/class/powercap/intel-rapl"


def format_value(num):
    # Formats a float to remove unnecessary trailing zeros.
    if num == int(num):
        return str(int(num))
    return f"{num:g}"


def write_value(path, value):
    """Writes a value to a file, using sudo if necessary, with minimal output."""
    try:
        with open(path, "w") as f:
            f.write(str(value))
    except PermissionError:
        try:
            subprocess.run(
                ["sudo", "tee", path],
                input=f"{value}\n",
                text=True,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        except FileNotFoundError:
            print(
                f"Error: 'sudo' or 'tee' command not found. Failed to write to {path}."
            )
            return False
        except subprocess.CalledProcessError as e:
            error_message = e.stderr.strip() if e.stderr else "Unknown error"
            print(f"Failed to write to {path} with sudo: {error_message}")
            return False
    except Exception as e:
        print(f"An unexpected error occurred while writing to {path}: {e}")
        return False
    return True


def read_and_format_file(file_path):
    # Reads a file, formats the value to SI units, and returns it.
    try:
        with open(file_path, "r") as f:
            value = f.read().strip()
            if value.isdigit():
                num_value = int(value)
                filename = os.path.basename(file_path)
                if "energy_uj" in filename:
                    return f"{format_value(num_value / 1_000_000)} J"
                if "_uw" in filename:
                    return f"{format_value(num_value / 1_000_000)} W"
                if "_us" in filename:
                    return f"{format_value(num_value / 1_000_000)} s"
            return value
    except (IOError, OSError):
        return None


def list_power_limits():
    if not os.path.isdir(RAPL_PATH):
        print("intel-rapl directory not found. Exiting.")
        return

    for rapl_dir in sorted(os.listdir(RAPL_PATH)):
        rapl_full_path = os.path.join(RAPL_PATH, rapl_dir)
        if not (os.path.isdir(rapl_full_path) and rapl_dir.startswith("intel-rapl:")):
            continue

        # Check if the device is enabled
        enabled_path = os.path.join(rapl_full_path, "enabled")
        if os.path.exists(enabled_path):
            with open(enabled_path, "r") as f:
                if f.read().strip() == "0":
                    continue  # Skip disabled devices

        print(f"Device: {rapl_dir}")

        files = sorted(os.listdir(rapl_full_path))
        constraints = defaultdict(dict)
        other_params = {}

        # Collect and group all parameters
        for item in files:
            full_item_path = os.path.join(rapl_full_path, item)
            if not os.path.isfile(full_item_path):
                continue

            value = read_and_format_file(full_item_path)
            if value is None:
                continue

            if item.startswith("constraint_"):
                parts = item.split("_", 2)
                if len(parts) == 3:
                    constraint_id = parts[1]
                    key = parts[2]
                    constraints[constraint_id][key] = value
            else:
                other_params[item] = value

        # Print other parameters first
        for key in sorted(other_params.keys()):
            if other_params[key]:
                print(f"  {key}: {other_params[key]}")

        # Print constraint blocks
        for constraint_id in sorted(constraints.keys()):
            constraint_data = constraints[constraint_id]
            name = constraint_data.pop("name", f"Unnamed Constraint {constraint_id}")

            # Skip empty constraints
            if not any(constraint_data.values()):
                continue

            print(f"\n  {name} (constraint {constraint_id}):")
            for key in sorted(constraint_data.keys()):
                if constraint_data[key]:
                    print(f"    {key}: {constraint_data[key]}")

        print()


def set_power_limits(rule, apply_to_all=False):
    """Sets power limits based on a rule string, with robust error handling."""
    if not os.path.isdir(RAPL_PATH):
        print("intel-rapl directory not found. Exiting.")
        return

    try:
        settings = dict(item.split("=") for item in rule.split(","))
    except ValueError:
        print("Invalid rule format. Use: peak=W,long=W,short=W,time=s")
        return

    power_map = {
        "peak": "constraint_0_power_limit_uw",
        "short": "constraint_0_power_limit_uw",
        "long": "constraint_1_power_limit_uw",
    }
    time_map = {"time": "constraint_0_time_window_us"}

    rapl_dirs = sorted(
        [d for d in os.listdir(RAPL_PATH) if d.startswith("intel-rapl:")]
    )
    if not rapl_dirs:
        print("No intel-rapl devices found.")
        return

    target_dirs = rapl_dirs if apply_to_all else [rapl_dirs[0]]

    for rapl_dir in target_dirs:
        print(f"Applying settings to {rapl_dir}:")
        for key, value_str in settings.items():
            try:
                path_suffix = None
                value_to_write = 0

                if key in power_map:
                    path_suffix = power_map[key]
                    value_to_write = int(float(value_str) * 1_000_000)
                elif key in time_map:
                    path_suffix = time_map[key]
                    value_to_write = int(float(value_str) * 1_000_000)

                if path_suffix:
                    path = os.path.join(RAPL_PATH, rapl_dir, path_suffix)
                    if os.path.exists(path):
                        if not write_value(path, value_to_write):
                            print(f"  Skipped setting {key} due to write error.")
                    else:
                        print(f"  Warning: Path not found, cannot set {key}: {path}")
            except ValueError:
                print(f"  Invalid numeric value for {key}: '{value_str}'")
            except Exception as e:
                print(f"  An unexpected error occurred while setting {key}: {e}")


def main():
    parser = argparse.ArgumentParser(
        description="Manage Intel RAPL power limits.",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog="This tool reads and writes values to the Linux power capping framework.\n"
        "Writing values typically requires root permissions.\n"
        "If not run as root, it will attempt to use 'sudo' for write operations.",
    )
    parser.add_argument(
        "-l",
        "--list",
        action="store_true",
        help="List all readable RAPL parameters in SI units.",
    )
    parser.add_argument(
        "-w",
        "--write",
        type=str,
        metavar="RULE",
        help="Write power limits using a rule string.\n"
        "The rule is a comma-separated list of key=value pairs.\n"
        'Example: -w "peak=90,long=75,time=2.5"',
    )
    parser.add_argument(
        "--all-devices",
        action="store_true",
        help="Apply the write rule to all RAPL devices (e.g., for multiple sockets).\n"
        "If not specified, the rule applies only to the first device found.",
    )

    args = parser.parse_args()

    if not os.path.isdir(RAPL_PATH):
        print(f"Intel RAPL directory not found at {RAPL_PATH}. Aborting.")
        return

    if args.list:
        list_power_limits()
    elif args.write:
        set_power_limits(args.write, args.all_devices)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
