from __future__ import annotations

import datetime as dt
import xml.etree.ElementTree as ET
from pathlib import Path

report_path = Path("reports/pytest-report.md")
junit_path = Path("pytest-report.xml")

now = dt.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

if not junit_path.exists():
    report_path.write_text(
        "# Pytest Results\n\n"
        f"Generated: {now}\n\n"
        "JUnit XML was not found. Pytest may have failed before writing test output.\n",
        encoding="utf-8",
    )
    raise SystemExit(0)

root = ET.parse(junit_path).getroot()

test_suites = [root] if root.tag == "testsuite" else root.findall("testsuite")

tests = sum(int(s.attrib.get("tests", 0)) for s in test_suites)
failures = sum(int(s.attrib.get("failures", 0)) for s in test_suites)
errors = sum(int(s.attrib.get("errors", 0)) for s in test_suites)
skipped = sum(int(s.attrib.get("skipped", 0)) for s in test_suites)
passed = tests - failures - errors - skipped
duration = sum(float(s.attrib.get("time", 0.0)) for s in test_suites)

lines = [
    "# Pytest Results",
    "",
    f"Generated: {now}",
    "",
    "## Summary",
    "",
    f"- Total: {tests}",
    f"- Passed: {passed}",
    f"- Failed: {failures}",
    f"- Errors: {errors}",
    f"- Skipped: {skipped}",
    f"- Duration: {duration:.2f}s",
    "",
]

failed_cases = []
for suite in test_suites:
    for case in suite.findall("testcase"):
        status = "passed"
        detail = ""

        failure = case.find("failure")
        error = case.find("error")
        skipped_node = case.find("skipped")

        if failure is not None:
            status = "failed"
            detail = (failure.text or failure.attrib.get("message") or "").strip()
        elif error is not None:
            status = "error"
            detail = (error.text or error.attrib.get("message") or "").strip()
        elif skipped_node is not None:
            status = "skipped"

        if status in {"failed", "error"}:
            classname = case.attrib.get("classname", "")
            name = case.attrib.get("name", "unknown")
            case_id = f"{classname}.{name}" if classname else name
            failed_cases.append((status, case_id, detail))

if failed_cases:
    lines.extend(
        [
            "## Failures",
            "",
        ]
    )
    for status, case_id, detail in failed_cases:
        lines.append(f"### {status.upper()}: {case_id}")
        lines.append("")
        if detail:
            lines.append("```")
            lines.append(detail[:4000])
            lines.append("```")
            lines.append("")
else:
    lines.extend(["## Failures", "", "No failing tests.", ""])

report_path.write_text("\n".join(lines), encoding="utf-8")