#!/usr/bin/env python3

import os
import sys
import json
import argparse
import subprocess

from time import sleep

CONFIG_PATH = "/etc/govctl/config.json"


def load_config() -> None:
    with open(CONFIG_PATH, "r") as f:
        return json.load(f)


def save_config(config) -> None:
    with open(CONFIG_PATH, "w") as f:
        json.dump(config, f, indent=4)


def reload_service() -> None:
    subprocess.run(["sudo", "systemctl", "reload", "govctl.service"], check=False)


def check_root() -> None:
    if os.geteuid():
        print("Root access required, rerun with sudo.", file=sys.stderr)
        sys.exit(1)


def get_cur_gov() -> None:
    try:
        output = subprocess.check_output(["systemctl", "status", "govctl"], text=True)
        last_lines = output.strip().splitlines()[-30:]
        last_lines.reverse()
        for line in last_lines:
            if "Applied governor" in line:
                return line[line.find('governor "') + 10 : -1]
    except:
        pass


def main() -> None:
    parser = argparse.ArgumentParser(description="Governor configuration tool")

    parser.add_argument(
        "-g",
        "--set-governor",
        choices=["powersave", "conservative", "performance"],
        help="Set desired governor",
    )

    parser.add_argument(
        "-G",
        "--get-governor",
        action="store_true",
        help="Get the saved governor for scripting (no newlines/formatting)",
    )

    parser.add_argument(
        "-b",
        "--set-battery-governor",
        choices=["powersave", "conservative", "performance"],
        help="Set desired governor while running on battery power",
    )

    parser.add_argument(
        "-e",
        "--enable-battery-detection",
        action="store_true",
        help="Enable battery state detection",
    )

    parser.add_argument(
        "-d",
        "--disable-battery-detection",
        action="store_true",
        help="Disable battery state detection",
    )

    parser.add_argument(
        "-p",
        "--powersave-percent",
        type=lambda x: (
            int(x)
            if 0 <= int(x) <= 80
            else (_ for _ in ()).throw(
                argparse.ArgumentTypeError(f"{x} not in range 0–80")
            )
        ),
        help="Percentage at which powersave triggers",
    )

    args = parser.parse_args()
    config = load_config()

    if args.get_governor:
        gov = get_cur_gov()
        print(gov if gov is not None else "Unknown", end="")
        sys.exit(0)

    modified = False

    if args.set_governor:
        config["governor"] = args.set_governor
        modified = True

    if args.set_battery_governor:
        config["governor_battery"] = args.set_battery_governor
        modified = True

    if args.enable_battery_detection:
        config["detect_battery_state"] = True
        modified = True

    if args.disable_battery_detection:
        config["detect_battery_state"] = False
        modified = True

    if args.powersave_percent:
        config["powersave_point"] = args.powersave_percent
        modified = True

    if modified:
        check_root()
        print("Saving configuration..")
        save_config(config)
        print("Reloading..")
        reload_service()
    else:
        gov = get_cur_gov()
        if gov is not None:
            info_str = "Currently applied governor: " + gov
            print(
                "\n"
                + ("-" * len(info_str))
                + "\n"
                + info_str
                + "\n"
                + ("-" * len(info_str))
                + "\n"
            )

        parser.print_help()


if __name__ == "__main__":
    main()
