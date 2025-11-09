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


def set_power_limits(rule, device=None):
    """Sets power limits based on a rule string, with robust error handling."""
    if not os.path.isdir(RAPL_PATH):
        print("Intel RAPL directory not found. Exiting.")
        return

    try:
        settings = {
            k.lower(): v for k, v in (item.split("=") for item in rule.split(","))
        }
    except ValueError:
        print(
            "Invalid rule format. Use: long=75,long_time=28,short=90,short_time=0.002"
        )
        return

    all_rapl_dirs = sorted(
        [d for d in os.listdir(RAPL_PATH) if d.startswith("intel-rapl:")]
    )

    target_dirs = []
    if device:
        if device in all_rapl_dirs:
            target_dirs.append(device)
        else:
            print(f"Error: Device '{device}' not found.")
            return
    else:
        # Default to all enabled devices
        for d in all_rapl_dirs:
            enabled_path = os.path.join(RAPL_PATH, d, "enabled")
            if os.path.exists(enabled_path):
                with open(enabled_path, "r") as f:
                    if f.read().strip() == "1":
                        target_dirs.append(d)

    if not target_dirs:
        print("No enabled RAPL devices found to apply settings to.")
        return

    for rapl_dir in target_dirs:
        print(f"Applying settings to {rapl_dir}:")
        rapl_full_path = os.path.join(RAPL_PATH, rapl_dir)

        # Dynamically build constraint map for the device
        constraint_map = {}
        for item in os.listdir(rapl_full_path):
            if item.endswith("_name"):
                name_path = os.path.join(rapl_full_path, item)
                with open(name_path, "r") as f:
                    name = f.read().strip()
                constraint_id = item.split("_")[1]
                if "long" in name:
                    constraint_map["long"] = f"constraint_{constraint_id}"
                elif "short" in name:
                    constraint_map["short"] = f"constraint_{constraint_id}"
                elif "peak" in name:
                    constraint_map["peak"] = f"constraint_{constraint_id}"

        for key, value_str in settings.items():
            try:
                path_suffix = None
                value_to_write = 0
                unit = ""

                if key.endswith("_time"):
                    constraint_name = key[:-5]
                    if constraint_name in constraint_map:
                        path_suffix = (
                            f"{constraint_map[constraint_name]}_time_window_us"
                        )
                        value_to_write = int(float(value_str) * 1_000_000)
                        unit = "s"
                elif key in constraint_map:
                    path_suffix = f"{constraint_map[key]}_power_limit_uw"
                    value_to_write = int(float(value_str) * 1_000_000)
                    unit = "W"

                if path_suffix:
                    path = os.path.join(rapl_full_path, path_suffix)
                    if os.path.exists(path):
                        if not write_value(path, value_to_write):
                            print(f"  Skipped setting {key} due to write error.")
                        else:
                            print(f"  Set {key} to {value_str}{unit}")
                    else:
                        print(f"  Warning: Path not found, cannot set {key}: {path}")
                else:
                    print(f"  Warning: Unknown setting '{key}'. Skipping.")
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
        help="List all readable RAPL parameters for enabled devices in SI units.",
    )
    parser.add_argument(
        "-w",
        "--write",
        type=str,
        metavar="RULE",
        help="Write power limits using a rule string.\n"
        "Applies to all enabled devices by default.\n"
        'Example: -w "long=75,long_time=28,short=90"',
    )
    parser.add_argument(
        "-d",
        "--device",
        type=str,
        help="Specify a target device for the write operation (e.g., intel-rapl:0).\n"
        "If specified, the rule applies only to this device.",
    )

    args = parser.parse_args()

    if not os.path.isdir(RAPL_PATH):
        print(f"Intel RAPL directory not found at {RAPL_PATH}. Aborting.")
        return

    if args.list:
        list_power_limits()
    elif args.write:
        set_power_limits(args.write, args.device)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
