#!/usr/bin/env python3

import json
import argparse
import subprocess

CONFIG_PATH = "/etc/govctl/config.json"


def load_config() -> None:
    with open(CONFIG_PATH, "r") as f:
        return json.load(f)


def save_config(config) -> None:
    with open(CONFIG_PATH, "w") as f:
        json.dump(config, f, indent=4)


def reload_service() -> None:
    subprocess.run(["systemctl", "reload", "governor.service"], check=False)


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

    args = parser.parse_args()
    config = load_config()

    if args.set_governor:
        config["governor"] = args.set_governor

    if args.enable_battery_detection:
        config["detect_battery_state"] = True

    if args.disable_battery_detection:
        config["detect_battery_state"] = False

    try:
        save_config(config)
    except:
        print(
            "Could not save to the configuration file, try running with sudo!\n\n`sudo !!`\n"
        )
    try:
        reload_service()
    except:
        print("Could not reload service!")


if __name__ == "__main__":
    main()
