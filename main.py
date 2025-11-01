#!/usr/bin/env python3
"""
Main entry point for firmware upgrade utilities.
Allows users to select between ADTRAN and COMTREND firmware upgrade tools.
"""

import sys


def display_menu():
    """Display the main menu options"""
    print("\n" + "=" * 50)
    print("FIRMWARE UPGRADE UTILITIES")
    print("=" * 50)
    print("1. Run ADTRAN firmware upgrader")
    print("2. Run COMTREND firmware upgrader")
    print("3. Exit")
    print("=" * 50)


def main():
    """Main entry point for the firmware upgrade utilities"""
    while True:
        display_menu()
        choice = input("\nSelect an option (1-3): ").strip()
        
        if choice == "1":
            print("\nStarting ADTRAN firmware upgrader...")
            try:
                import adtranfirmwareupgrader
                adtranfirmwareupgrader.main()
            except ImportError as e:
                print(f"Error: Could not import adtranfirmwareupgrader module: {e}")
                print("Please ensure adtranfirmwareupgrader.py exists in the same directory.")
            except Exception as e:
                print(f"Error running ADTRAN firmware upgrader: {e}")
        
        elif choice == "2":
            print("\nStarting COMTREND firmware upgrader...")
            try:
                import comtrendfirmwareupgrader
                comtrendfirmwareupgrader.main()
            except ImportError as e:
                print(f"Error: Could not import comtrendfirmwareupgrader module: {e}")
                print("Please ensure comtrendfirmwareupgrader.py exists in the same directory.")
            except Exception as e:
                print(f"Error running COMTREND firmware upgrader: {e}")
        
        elif choice == "3":
            print("\nExiting...")
            sys.exit(0)
        
        else:
            print("\nInvalid choice. Please select 1, 2, or 3.")
        
        # After a script completes, ask if user wants to return to menu or exit
        if choice in ["1", "2"]:
            continue_choice = input("\nReturn to main menu? (y/n): ").strip().lower()
            if continue_choice not in ["y", "yes"]:
                print("\nExiting...")
                sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nExiting program...")
        sys.exit(0)

