"""
Run all E2E tests for Lattice Cast Backend

Usage:
    python tests/run_all_tests.py

Runs:
    - e2e_auth_test.py - Authentication tests
    - e2e_storage_test.py - Storage tests
"""

import sys
from pathlib import Path

# Add tests directory to path
tests_dir = Path(__file__).parent
sys.path.insert(0, str(tests_dir))

from e2e_auth_test import run_all_tests as run_auth_tests
from e2e_storage_test import run_all_tests as run_storage_tests


def main():
    print("\n" + "=" * 70)
    print("                    LATTICE_CAST BACKEND E2E TESTS")
    print("=" * 70)

    try:
        # Run auth tests first
        print("\n[1/2] Running Authentication Tests...")
        run_auth_tests()

        # Run storage tests
        print("\n[2/2] Running Storage Tests...")
        run_storage_tests()

        print("\n" + "=" * 70)
        print("                    ALL TESTS PASSED!")
        print("=" * 70 + "\n")

    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
