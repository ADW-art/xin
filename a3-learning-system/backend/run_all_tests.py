"""
A3 Unified Test Runner

Usage:
  python run_all_tests.py                  # Run all tests
  python run_all_tests.py --coverage       # With coverage report
  python run_all_tests.py --verbose        # Verbose output
  python run_all_tests.py --module bkt     # Filter by module name
"""
import sys
import os
import argparse
import subprocess
import time


def run_tests(module_filter: str = "", coverage: bool = False, verbose: bool = False) -> int:
    project_root = os.path.dirname(os.path.abspath(__file__))
    os.chdir(project_root)

    pytest_args = ["-x"]
    if verbose:
        pytest_args.append("-v")
    if coverage:
        pytest_args.extend(["--cov=app", "--cov-report=term-missing", "--cov-report=html"])

    test_dir = os.path.join(project_root, "tests")
    if not os.path.isdir(test_dir):
        print(f"[ERROR] Test directory not found: {test_dir}")
        return 1

    all_test_files = sorted([
        os.path.join(test_dir, f)
        for f in os.listdir(test_dir)
        if f.startswith("test_") and f.endswith(".py")
    ])

    if module_filter:
        filtered = [f for f in all_test_files if module_filter.lower() in os.path.basename(f).lower()]
        if not filtered:
            print(f"[WARN] No test files match filter '{module_filter}'")
            available = [os.path.basename(f).replace("test_", "").replace(".py", "") for f in all_test_files]
            print(f"  Available modules: {', '.join(available)}")
            return 0
        test_files = filtered
    else:
        test_files = all_test_files

    print("=" * 60)
    print(f"A3 Unified Test Suite")
    print(f"  Directory: {project_root}")
    print(f"  Files:     {len(test_files)}")
    print(f"  Coverage:  {'enabled' if coverage else 'disabled'}")
    print(f"  Verbose:   {'yes' if verbose else 'no'}")
    print("-" * 60)
    for f in test_files:
        print(f"  {os.path.basename(f)}")
    print("=" * 60)

    start_time = time.time()
    cmd = [sys.executable, "-m", "pytest"] + test_files + pytest_args
    result = subprocess.run(cmd, capture_output=False, text=True)
    elapsed = time.time() - start_time

    print(f"\n{'=' * 60}")
    status = "ALL PASSED" if result.returncode == 0 else "FAILURES DETECTED"
    print(f"Test run {status} | Elapsed: {elapsed:.1f}s | Exit code: {result.returncode}")
    print(f"{'=' * 60}")
    return result.returncode


def main():
    parser = argparse.ArgumentParser(description="A3 Unified Test Runner")
    parser.add_argument("--module", "-m", default="", help="Module filter (bkt/rag/kg/auth/agent)")
    parser.add_argument("--coverage", "-c", action="store_true", help="Enable coverage report")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    args = parser.parse_args()
    sys.exit(run_tests(module_filter=args.module, coverage=args.coverage, verbose=args.verbose))


if __name__ == "__main__":
    main()
