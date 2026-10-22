#!/usr/bin/env python3
"""Machine-counted unittest discovery. Empty and wholly skipped suites fail."""
import argparse
import json
from pathlib import Path
import sys
import unittest


class CountedResult(unittest.TextTestResult):
    passed = 0

    def addSuccess(self, test):
        super().addSuccess(test)
        self.passed += 1


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--directory", required=True)
    p.add_argument("--pattern", default="test_*.py")
    p.add_argument("--report", required=True, type=Path)
    args = p.parse_args()
    suite = unittest.defaultTestLoader.discover(args.directory, pattern=args.pattern)
    discovered = suite.countTestCases()
    result = unittest.TextTestRunner(verbosity=2, resultclass=CountedResult).run(suite)
    # Fixture errors and subtest failures are events, not executed test cases.
    passed = result.passed
    report = {"discovered": discovered, "executed": result.testsRun, "passed": passed,
              "skipped": len(result.skipped), "failed": len(result.errors) + len(result.failures),
              "expected_failures": len(result.expectedFailures), "unexpected_successes": len(result.unexpectedSuccesses)}
    report["status"] = "passed" if discovered > 0 and passed > 0 and result.wasSuccessful() and not result.expectedFailures else "failed"
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
