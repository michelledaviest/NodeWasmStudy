#!/usr/bin/env python3
"""
Adds "test_scripts" to each entry in "wasm_module_details" in dataset/node-wasm-set.json.

For each wasm hash, scans all per-test dynamic logs in data/dynamic-results/<package>/
and records which test scripts instantiated that wasm module.
"""

import gzip
import json
import os

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DATASET_PATH = os.path.join(REPO_ROOT, "dataset/node-wasm-set.json")
DYNAMIC_RESULTS_DIR = os.path.join(REPO_ROOT, "data/dynamic-results")

INSTANTIATE_MARKER = "WebAssemblyInstantiateWithHash"


def get_test_scripts_per_hash(package_name: str) -> dict:
    """
    Returns {hash: [test_script_names]} by scanning all .json.gz log files
    in the dynamic-results folder for this package.
    """
    folder = os.path.join(DYNAMIC_RESULTS_DIR, package_name.replace("/", "__"))
    if not os.path.isdir(folder):
        return {}

    hash_to_tests = {}

    for filename in os.listdir(folder):
        if not filename.endswith(".json.gz"):
            continue
        filepath = os.path.join(folder, filename)
        try:
            with gzip.open(filepath) as f:
                data = json.load(f)
        except Exception:
            continue

        per_test_log = data.get("log", {})
        for test_name, test_data in per_test_log.items():
            for line in test_data.get("log", []):
                if INSTANTIATE_MARKER not in line:
                    continue
                parts = line.split("__,__")
                if len(parts) >= 3:
                    h = parts[2].strip()
                    hash_to_tests.setdefault(h, set()).add(test_name)

    return hash_to_tests


def main():
    with open(DATASET_PATH) as f:
        dataset = json.load(f)

    for package_name, package_data in dataset.items():
        module_details = package_data.get("wasm_module_details", {})
        if not module_details:
            continue

        hash_to_tests = get_test_scripts_per_hash(package_name)

        for h, details in module_details.items():
            details["test_scripts"] = sorted(hash_to_tests.get(h, set()))

    with open(DATASET_PATH, "w") as f:
        json.dump(dataset, f, indent=2)

    total_with_tests = sum(
        1
        for pkg in dataset.values()
        for details in pkg.get("wasm_module_details", {}).values()
        if details.get("test_scripts")
    )
    total_modules = sum(len(pkg.get("wasm_module_details", {})) for pkg in dataset.values())
    print(f"Updated {len(dataset)} packages ({total_modules} wasm modules, {total_with_tests} with test scripts)")


if __name__ == "__main__":
    main()
