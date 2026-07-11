"""完整回归测试: 一键验证今日 4 个 bug 修复

运行: python scripts/master_regression_test.py
"""
import subprocess
import sys
import time
from pathlib import Path

BACKEND = Path(r"E:\code\claude-1\a3-learning-system\backend")
VENV_PY = BACKEND / "venv" / "Scripts" / "python.exe"

tests = [
    ("1. 静态验证 (syntax/import/config)", "scripts/test_step1_static.py"),
    ("2-5. 单元测试 (4 个 bug 修复)", "scripts/test_step2_unit.py"),
]


def run_test(name, script, timeout=60):
    print(f"\n{'=' * 60}")
    print(f"  跑测试: {name}")
    print(f"  脚本: {script}")
    print("=" * 60)
    start = time.time()
    try:
        result = subprocess.run(
            [str(VENV_PY), script],
            cwd=str(BACKEND),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        elapsed = time.time() - start
        # 输出后 60 行 (PowerShell 限制)
        output_lines = result.stdout.splitlines()[-60:]
        print("\n".join(output_lines))
        if result.returncode == 0:
            print(f"\n  [PASS] {name} (耗时 {elapsed:.1f}s)")
            return True, elapsed
        else:
            print(f"\n  [FAIL] {name} (returncode={result.returncode}, 耗时 {elapsed:.1f}s)")
            return False, elapsed
    except subprocess.TimeoutExpired:
        elapsed = time.time() - start
        print(f"\n  [TIMEOUT] {name} (耗时 {elapsed:.1f}s)")
        return False, elapsed
    except Exception as e:
        elapsed = time.time() - start
        print(f"\n  [ERR] {name}: {e}")
        return False, elapsed


if __name__ == "__main__":
    print("=" * 60)
    print("  完整回归测试 - 4 个 Bug 修复")
    print("=" * 60)

    results = []
    for name, script in tests:
        ok, elapsed = run_test(name, script, timeout=120)
        results.append((name, ok, elapsed))

    print("\n" + "=" * 60)
    print("  回归测试总览")
    print("=" * 60)
    total = len(results)
    passed = sum(1 for _, ok, _ in results if ok)
    for name, ok, elapsed in results:
        status = "OK" if ok else "FAIL"
        print(f"  [{status}] {name} ({elapsed:.1f}s)")
    print(f"\n  通过: {passed}/{total}")

    sys.exit(0 if passed == total else 1)
