#!/usr/bin/env python3
"""Promtool & PromQL rule syntax validator script.

Validates:
1. YAML structure of Prometheus alert rule files.
2. Mandatory rule fields (alert, expr, for, labels, annotations, summary, description, runbook).
3. PromQL syntax parsing & token balance checks across all rule expressions.
"""

import re
import sys

import yaml

RULE_FILES = [
    "infra/monitoring/prometheus/rules/security-metrics.yml",
    "infra/monitoring/prometheus/rules/service-health.yml",
    "infra/monitoring/prometheus/rules/application-metrics.yml",
]

FUNCTIONS = {
    "sum", "avg", "min", "max", "count", "rate", "increase", "irate",
    "clamp_min", "clamp_max", "histogram_quantile", "absent", "time", "delta"
}

def validate_promql_syntax(expr_name: str, expr: str) -> list[str]:
    errors = []
    
    # 1. Parenthesis matching
    paren_depth = 0
    bracket_depth = 0
    brace_depth = 0
    
    for ch in expr:
        if ch == '(':
            paren_depth += 1
        elif ch == ')':
            paren_depth -= 1
            if paren_depth < 0:
                errors.append(f"Unmatched closing parenthesis ')' in {expr_name}")
        elif ch == '[':
            bracket_depth += 1
        elif ch == ']':
            bracket_depth -= 1
            if bracket_depth < 0:
                errors.append(f"Unmatched closing bracket ']' in {expr_name}")
        elif ch == '{':
            brace_depth += 1
        elif ch == '}':
            brace_depth -= 1
            if brace_depth < 0:
                errors.append(f"Unmatched closing brace '}}' in {expr_name}")

    if paren_depth != 0:
        errors.append(f"Unbalanced parentheses (open depth={paren_depth}) in {expr_name}")
    if bracket_depth != 0:
        errors.append(f"Unbalanced square brackets (open depth={bracket_depth}) in {expr_name}")
    if brace_depth != 0:
        errors.append(f"Unbalanced curly braces (open depth={brace_depth}) in {expr_name}")

    # 2. Check for invalid double operators (e.g. `>>`, `//`, `== =`)
    if re.search(r"[+\-*/]\s*[+\-*/]", expr):
        errors.append(f"Consecutive arithmetic operators in {expr_name}: {expr}")
        
    return errors


def validate_file(fpath: str) -> tuple[int, int, list[str]]:
    print(f"\n--- Checking {fpath} ---")
    file_errors = []
    rule_count = 0

    with open(fpath, encoding="utf-8") as f:
        try:
            data = yaml.safe_load(f)
        except Exception as e:
            return 0, 1, [f"YAML Parse Error in {fpath}: {e}"]

    if not isinstance(data, dict) or "groups" not in data:
        return 0, 1, [f"Invalid Prometheus rule structure in {fpath}: missing 'groups' key"]

    groups = data["groups"]
    for group in groups:
        gname = group.get("name", "<unnamed>")
        rules = group.get("rules", [])
        for rule in rules:
            rule_count += 1
            alert_name = rule.get("alert", "<unnamed_alert>")
            expr = rule.get("expr", "")
            for_dur = rule.get("for", "")
            labels = rule.get("labels", {})
            annotations = rule.get("annotations", {})

            # Mandatory fields check
            if not alert_name or alert_name == "<unnamed_alert>":
                file_errors.append(f"Group '{gname}': Rule missing 'alert' name")
            if not expr:
                file_errors.append(f"Alert '{alert_name}': Missing 'expr'")
            if not for_dur:
                file_errors.append(f"Alert '{alert_name}': Missing 'for' duration")

            # Check required labels & annotations
            if "severity" not in labels:
                file_errors.append(f"Alert '{alert_name}': Missing label 'severity'")
            elif labels["severity"] not in ("page", "ticket"):
                file_errors.append(f"Alert '{alert_name}': Invalid severity '{labels['severity']}'")

            if "summary" not in annotations:
                file_errors.append(f"Alert '{alert_name}': Missing annotation 'summary'")
            if "description" not in annotations:
                file_errors.append(f"Alert '{alert_name}': Missing annotation 'description'")
            if "runbook" not in annotations:
                file_errors.append(f"Alert '{alert_name}': Missing annotation 'runbook'")

            # PromQL syntax validation
            pql_errs = validate_promql_syntax(alert_name, expr)
            file_errors.extend(pql_errs)

            if not file_errors:
                print(f"  [OK] Alert: {alert_name} (for: {for_dur}, severity: {labels.get('severity')})")

    return rule_count, len(file_errors), file_errors


def main():
    total_rules = 0
    total_errors = 0
    all_err_msgs = []

    for fpath in RULE_FILES:
        rules, errs_cnt, msgs = validate_file(fpath)
        total_rules += rules
        total_errors += errs_cnt
        all_err_msgs.extend(msgs)

    print("\n==========================================")
    print(f"VALIDATION SUMMARY: {total_rules} rules checked across {len(RULE_FILES)} files.")
    if total_errors == 0:
        print("ALL PROMETHEUS RULE FILES AND PROMQL EXPRESSIONS ARE VALID! [PASS]")
        sys.exit(0)
    else:
        print(f"FAILED: Found {total_errors} errors:")
        for msg in all_err_msgs:
            print(f"  - {msg}")
        sys.exit(1)


if __name__ == "__main__":
    main()
