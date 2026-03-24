#!/usr/bin/env python3
"""
Adds "wasm_execution_metadata" to each package in dataset/node-wasm-set.json.

For each package:
  - wasm_instantiated: True if a wasm hash found in data/dumped-wasm-files/<package>/
                       has Init > 0 in wasm-modules-interop-type.json for that package.
  - wasm_executed:     True if the same condition holds and CallExportedFunc > 0.
"""

import json
import os

DATASET_PATH = os.path.join(os.path.dirname(__file__), "../dataset/node-wasm-set.json")
INTEROP_PATH = os.path.join(os.path.dirname(__file__), "../data/summary-json/wasm-modules-interop-type.json")
DUMPED_WASM_DIR = os.path.join(os.path.dirname(__file__), "../data/dumped-wasm-files")


def get_dumped_hashes(package_name: str) -> set:
    """Return the set of wasm hashes present in the dumped-wasm-files folder for this package."""
    folder_name = package_name.replace("/", "__")
    folder_path = os.path.join(DUMPED_WASM_DIR, folder_name)
    if not os.path.isdir(folder_path):
        return set()
    hashes = set()
    for filename in os.listdir(folder_path):
        # Files are named: realwasm-module-<hash>.wasm
        if filename.startswith("realwasm-module-") and filename.endswith(".wasm"):
            h = filename[len("realwasm-module-"):-len(".wasm")]
            hashes.add(h)
    return hashes


def compute_metadata(package_name: str, interop_data: dict) -> dict:
    dumped_hashes = get_dumped_hashes(package_name)
    wasm_instantiated = False
    wasm_executed = False

    for wasm_hash, packages in interop_data.items():
        if wasm_hash not in dumped_hashes:
            continue
        if package_name not in packages:
            continue
        for lib_info in packages[package_name].values():
            interop_type = lib_info.get("interop_type", {})
            if interop_type.get("Init", 0) > 0:
                wasm_instantiated = True
            if interop_type.get("CallExportedFunc", 0) > 0:
                wasm_executed = True

    return {
        "wasm_instantiated": wasm_instantiated,
        "wasm_executed": wasm_executed,
    }


def main():
    with open(DATASET_PATH) as f:
        dataset = json.load(f)

    with open(INTEROP_PATH) as f:
        interop_data = json.load(f)

    for package_name, package_data in dataset.items():
        package_data["wasm_execution_metadata"] = compute_metadata(package_name, interop_data)

    with open(DATASET_PATH, "w") as f:
        json.dump(dataset, f, indent=2)

    print(f"Updated {len(dataset)} packages in {DATASET_PATH}")


if __name__ == "__main__":
    main()
