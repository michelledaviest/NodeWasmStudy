#!/usr/bin/env python3
"""
Adds "wasm_module_details" to each package in dataset/node-wasm-set.json.

For each dumped wasm file belonging to a package, records:
  - size_bytes:                 size of the wasm binary
  - dump_path:                  absolute path to the dumped wasm file
  - static_paths:               list of absolute static paths where this wasm was found,
                                or null if no static location was found
  - exported_functions_called:  list of unique exported function names called at runtime
"""

import json
import os

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DATASET_PATH = os.path.join(REPO_ROOT, "dataset/node-wasm-set.json")
STATIC_LOCATION_PATH = os.path.join(REPO_ROOT, "data/statically-locate-dynamic-wasm/all-clients-with-dumps-all-files.json")
EXPORTS_CALLED_PATH = os.path.join(REPO_ROOT, "data/summary-json/exports-called-count.json")
DUMPED_WASM_DIR = os.path.join(REPO_ROOT, "data/dumped-wasm-files")


def build_static_paths_lookup(static_data: dict) -> dict:
    """Returns {package_name: {hash: [absolute_static_paths]}}."""
    lookup = {}
    for report in static_data.get("reports", []):
        pkg = report["package"]
        lookup[pkg] = {}
        for h, matches in report.get("hash_to_matches", {}).items():
            lookup[pkg][h] = matches
    return lookup


def build_exports_called_lookup(exports_data: dict) -> dict:
    """Returns {package_name: {hash: set_of_function_names}}."""
    lookup = {}
    for lib, packages in exports_data.items():
        for pkg, hashes in packages.items():
            for h, funcs in hashes.items():
                lookup.setdefault(pkg, {}).setdefault(h, set()).update(funcs.keys())
    return lookup


def get_wasm_hashes(package_name: str) -> list:
    """Returns list of (hash, absolute_dump_path) for all dumped wasm files of a package."""
    folder = os.path.join(DUMPED_WASM_DIR, package_name.replace("/", "__"))
    if not os.path.isdir(folder):
        return []
    results = []
    for filename in os.listdir(folder):
        if filename.startswith("realwasm-module-") and filename.endswith(".wasm"):
            h = filename[len("realwasm-module-"):-len(".wasm")]
            abs_path = os.path.join(folder, filename)
            results.append((h, os.path.relpath(abs_path, REPO_ROOT)))
    return results


def main():
    with open(DATASET_PATH) as f:
        dataset = json.load(f)

    with open(STATIC_LOCATION_PATH) as f:
        static_data = json.load(f)

    with open(EXPORTS_CALLED_PATH) as f:
        exports_data = json.load(f)

    static_lookup = build_static_paths_lookup(static_data)
    exports_lookup = build_exports_called_lookup(exports_data)

    for package_name, package_data in dataset.items():
        wasm_hashes = get_wasm_hashes(package_name)
        module_details = {}

        for h, dump_path in wasm_hashes:
            pkg_static = static_lookup.get(package_name, {})
            static_paths = pkg_static.get(h, None)

            called_funcs = exports_lookup.get(package_name, {}).get(h, set())

            module_details[h] = {
                "size_bytes": os.path.getsize(os.path.join(REPO_ROOT, dump_path)),
                "dump_path": dump_path,
                "static_paths": static_paths,
                "exported_functions_called": sorted(called_funcs),
            }

        package_data["wasm_module_details"] = module_details

    with open(DATASET_PATH, "w") as f:
        json.dump(dataset, f, indent=2)

    total_modules = sum(len(v["wasm_module_details"]) for v in dataset.values())
    print(f"Updated {len(dataset)} packages ({total_modules} wasm modules) in {DATASET_PATH}")


if __name__ == "__main__":
    main()
