#!/usr/bin/env python3
"""
Main entry point for firmware upgrade utilities.
Allows users to select between ADTRAN and COMTREND firmware upgrade tools.
"""

import sys
from simple_term_menu import TerminalMenu

from network_utils import drain_tty_input, reset_tty_sane


def main():
    """Main entry point for the firmware upgrade utilities"""
    while True:
        main_options = [
            "Run ADTRAN firmware upgrader",
            "Run COMTREND firmware upgrader",
            "Exit",
        ]
        main_menu = TerminalMenu(main_options, title="FIRMWARE UPGRADE UTILITIES")
        choice_index = main_menu.show()
        drain_tty_input()

        if choice_index is None or choice_index == 2:
            print("\nExiting...")
            sys.exit(0)

        if choice_index == 0:
            print("\nStarting ADTRAN firmware upgrader...")
            try:
                import adtranfirmwareupgrader
                adtranfirmwareupgrader.main()
            except ImportError as e:
                print(f"Error: Could not import adtranfirmwareupgrader module: {e}")
                print("Please ensure adtranfirmwareupgrader.py exists in the same directory.")
            except Exception as e:
                print(f"Error running ADTRAN firmware upgrader: {e}")

        elif choice_index == 1:
            print("\nStarting COMTREND firmware upgrader...")
            try:
                import comtrendfirmwareupgrader
                comtrendfirmwareupgrader.main()
            except ImportError as e:
                print(f"Error: Could not import comtrendfirmwareupgrader module: {e}")
                print("Please ensure comtrendfirmwareupgrader.py exists in the same directory.")
            except Exception as e:
                print(f"Error running COMTREND firmware upgrader: {e}")

        # Flush output and reset terminal before next menu to avoid lag
        sys.stdout.flush()
        sys.stderr.flush()
        reset_tty_sane()
        return_options = ["Yes", "No"]
        return_menu = TerminalMenu(return_options, title="Return to main menu?")
        return_index = return_menu.show()
        drain_tty_input()
        if return_index != 0:
            print("\nExiting...")
            sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nExiting program...")
        sys.exit(0)
