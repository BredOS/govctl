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


def main() -> None:
    parser = argparse.ArgumentParser(description="Governor configuration tool")
    parser.add_argument(
        "-g",
        "--set-governor",
        choices=["powersave", "conservative", "performance"],
        help="Set desired governor",
    )
    parser.add_argument(
        "-b",
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

    modified = False

    if args.set_governor:
        config["governor"] = args.set_governor
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
        for _ in range(3):
            try:
                output = subprocess.check_output(
                    ["systemctl", "status", "govctl"], text=True
                )
                last_line = output.strip().splitlines()[-1]
                if "Applied governor" in last_line:
                    info_str = (
                        "Currently applied governor: "
                        + last_line[last_line.find('governor "') + 10 : -1]
                    )
                    print(
                        "\n"
                        + ("-" * len(info_str))
                        + "\n"
                        + info_str
                        + "\n"
                        + ("-" * len(info_str))
                        + "\n"
                    )
                    break
            except subprocess.CalledProcessError:
                pass
            sleep(1)

        parser.print_help()


if __name__ == "__main__":
    main()
