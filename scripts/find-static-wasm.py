#!/usr/bin/env python3

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

from find_wasm import find_files_with_any_wasm_hash, find_files_with_wasm_hash


_ALL_SCAN_SUFFIXES = {".wasm", ".js", ".mjs", ".cjs", ".ts", ".mts", ".cts"}


def _default_dataset_path() -> Path:
    return Path("~/NodeWasmStudy/dataset/node-wasm-set.json").expanduser()


def _default_dumped_root() -> Path:
    return Path("~/NodeWasmStudy/data/dumped-wasm-files").expanduser()


def _default_packages_root() -> Path:
    return Path("~/NodeWasmPackages").expanduser()


def _owner_repo_to_client_name(owner_repo: str) -> str:
    return owner_repo.replace("/", "__")


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _load_dataset(dataset_path: Path) -> dict:
    with dataset_path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _load_dataset_entry(dataset_path: Path, package_name: str) -> dict:
    dataset = _load_dataset(dataset_path)

    if package_name not in dataset:
        raise KeyError(f"Package '{package_name}' not found in {dataset_path}")

    return dataset[package_name]


def _client_name_to_owner_repo(client_name: str) -> str:
    return client_name.replace("__", "/", 1)


def _collect_dump_hashes(dump_dir: Path) -> List[str]:
    if not dump_dir.is_dir():
        raise FileNotFoundError(f"Dump directory not found: {dump_dir}")

    hashes: List[str] = []
    for path in sorted(dump_dir.glob("*.wasm")):
        try:
            hashes.append(_sha256_bytes(path.read_bytes()))
        except OSError:
            continue

    return hashes


def _collect_dataset_static_candidates(entry: dict, package_root: Path) -> List[str]:
    static_paths = (
        entry.get("wasm_dependencies", {}).get("files_with_wasm", [])
        if isinstance(entry, dict)
        else []
    )

    candidates: List[str] = []
    for rel in static_paths:
        full_path = package_root / rel
        if full_path.is_file() and full_path.suffix.lower() in _ALL_SCAN_SUFFIXES:
            candidates.append(str(full_path))
    return candidates


def _collect_all_package_candidates(package_root: Path, progress: bool = False) -> List[str]:
    candidates: List[str] = []
    visited = 0
    for path in package_root.rglob("*"):
        visited += 1
        if path.is_file() and path.suffix.lower() in _ALL_SCAN_SUFFIXES:
            candidates.append(str(path))
        if progress and visited % 5000 == 0:
            print(
                f"[test_dataset_find_wasm] visited {visited} paths, found {len(candidates)} candidates",
                file=sys.stderr,
            )

    if progress:
        print(
            f"[test_dataset_find_wasm] finished collecting candidates: {len(candidates)} files",
            file=sys.stderr,
        )
    return candidates


def _iter_dumped_clients(dumped_root: Path) -> List[str]:
    clients: List[str] = []
    if not dumped_root.is_dir():
        raise FileNotFoundError(f"Dumped root not found: {dumped_root}")

    for path in sorted(dumped_root.iterdir()):
        if not path.is_dir():
            continue
        if any(path.glob("*.wasm")):
            clients.append(path.name)
    return clients


def run_test(
    dataset_path: Path,
    package_name: str,
    dumped_root: Path,
    packages_root: Path,
    scan_all_package_files: bool,
    workers: int | None,
    progress: bool,
    dataset: dict[str, Any] | None = None,
) -> dict:
    if dataset is None:
        entry = _load_dataset_entry(dataset_path, package_name)
    else:
        if package_name not in dataset:
            raise KeyError(f"Package '{package_name}' not found in {dataset_path}")
        entry = dataset[package_name]
    client_name = _owner_repo_to_client_name(package_name)
    dump_dir = dumped_root / client_name
    package_root = packages_root / client_name

    if not package_root.is_dir():
        raise FileNotFoundError(f"Package directory not found: {package_root}")

    dumped_hashes = _collect_dump_hashes(dump_dir)

    if progress:
        print(
            f"[test_dataset_find_wasm] loaded {len(dumped_hashes)} dumped wasm hashes from {dump_dir}",
            file=sys.stderr,
        )

    if scan_all_package_files:
        candidate_paths = _collect_all_package_candidates(package_root, progress=progress)
        scan_mode = "all-package-files"
    else:
        candidate_paths = _collect_dataset_static_candidates(entry, package_root)
        scan_mode = "dataset-static-files"
        if progress:
            print(
                f"[test_dataset_find_wasm] using {len(candidate_paths)} dataset-listed candidate files",
                file=sys.stderr,
            )

    requested_workers = workers if workers is not None else max(1, os.cpu_count() or 1)
    effective_workers = max(1, min(requested_workers, 32))

    if progress:
        print(
            f"[test_dataset_find_wasm] scan mode: {scan_mode}, workers: {effective_workers}",
            file=sys.stderr,
        )

    if scan_all_package_files:
        raw_hash_to_matches = find_files_with_any_wasm_hash(
            target_hashes=dumped_hashes,
            file_paths=candidate_paths,
            workers=effective_workers,
            progress=progress,
        )
    else:
        raw_hash_to_matches: Dict[str, List[str]] = {}
        total_hashes = len(dumped_hashes)
        for index, wasm_hash in enumerate(dumped_hashes, start=1):
            if progress:
                print(
                    f"[test_dataset_find_wasm] matching hash {index}/{total_hashes}",
                    file=sys.stderr,
                )
            raw_hash_to_matches[wasm_hash] = find_files_with_wasm_hash(wasm_hash, candidate_paths)

    hash_to_matches: Dict[str, List[str]] = {}
    for wasm_hash, matches in raw_hash_to_matches.items():
        hash_to_matches[wasm_hash] = [
            str(Path(match).relative_to(package_root)) if str(match).startswith(str(package_root)) else match
            for match in matches
        ]

    matched_hashes = [h for h, m in hash_to_matches.items() if m]
    unmatched_hashes = [h for h, m in hash_to_matches.items() if not m]

    matched_static_files = sorted({path for matches in hash_to_matches.values() for path in matches})

    return {
        "package": package_name,
        "client_name": client_name,
        "scan_mode": scan_mode,
        "dataset_path": str(dataset_path),
        "package_root": str(package_root),
        "dump_dir": str(dump_dir),
        "dumped_wasm_count": len(dumped_hashes),
        "candidate_file_count": len(candidate_paths),
        "workers": effective_workers,
        "matched_hash_count": len(matched_hashes),
        "unmatched_hash_count": len(unmatched_hashes),
        "matched_static_files": matched_static_files,
        "hash_to_matches": hash_to_matches,
        "unmatched_hashes": unmatched_hashes,
    }


def run_all_tests(
    dataset_path: Path,
    dumped_root: Path,
    packages_root: Path,
    scan_all_package_files: bool,
    workers: int | None,
    progress: bool,
) -> dict:
    dataset = _load_dataset(dataset_path)
    dumped_clients = _iter_dumped_clients(dumped_root)
    requested_workers = workers if workers is not None else max(1, os.cpu_count() or 1)
    effective_workers = max(1, min(requested_workers, 32))
    reports: List[dict[str, Any]] = []
    failures: List[dict[str, str]] = []

    for index, client_name in enumerate(dumped_clients, start=1):
        package_name = _client_name_to_owner_repo(client_name)

        if progress:
            print(
                f"[test_dataset_find_wasm] package {index}/{len(dumped_clients)}: {package_name}",
                file=sys.stderr,
            )

        if package_name not in dataset:
            failures.append(
                {
                    "client_name": client_name,
                    "package": package_name,
                    "error": f"Package not found in dataset: {package_name}",
                }
            )
            continue

        try:
            report = run_test(
                dataset_path=dataset_path,
                package_name=package_name,
                dumped_root=dumped_root,
                packages_root=packages_root,
                scan_all_package_files=scan_all_package_files,
                workers=effective_workers,
                progress=progress,
                dataset=dataset,
            )
            reports.append(report)
        except Exception as exc:
            failures.append(
                {
                    "client_name": client_name,
                    "package": package_name,
                    "error": str(exc),
                }
            )

    total_dumped_wasm_count = sum(report["dumped_wasm_count"] for report in reports)
    total_matched_hash_count = sum(report["matched_hash_count"] for report in reports)
    total_unmatched_hash_count = sum(report["unmatched_hash_count"] for report in reports)

    fully_matched_packages = sum(1 for report in reports if report["unmatched_hash_count"] == 0)
    partially_matched_packages = sum(1 for report in reports if 0 < report["matched_hash_count"] < report["dumped_wasm_count"])
    no_match_packages = sum(1 for report in reports if report["matched_hash_count"] == 0)

    return {
        "mode": "all-dumped-clients",
        "dataset_path": str(dataset_path),
        "dumped_root": str(dumped_root),
        "packages_root": str(packages_root),
        "scan_mode": "all-package-files" if scan_all_package_files else "dataset-static-files",
        "workers": effective_workers,
        "client_count": len(dumped_clients),
        "successful_package_count": len(reports),
        "failed_package_count": len(failures),
        "total_dumped_wasm_count": total_dumped_wasm_count,
        "total_matched_hash_count": total_matched_hash_count,
        "total_unmatched_hash_count": total_unmatched_hash_count,
        "fully_matched_packages": fully_matched_packages,
        "partially_matched_packages": partially_matched_packages,
        "no_match_packages": no_match_packages,
        "failures": failures,
        "reports": reports,
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Test find_wasm.py against dataset metadata and dumped runtime Wasm files "
            "for a package (default: httptoolkit/mockttp)."
        )
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=_default_dataset_path(),
        help="Path to node-wasm-set.json",
    )
    parser.add_argument(
        "--package",
        default="httptoolkit/mockttp",
        help="Package key in dataset (owner/repo)",
    )
    parser.add_argument(
        "--all-dumped-clients",
        action="store_true",
        help="Run against every client directory under dumped-wasm-files that contains dumped .wasm files",
    )
    parser.add_argument(
        "--dumped-root",
        type=Path,
        default=_default_dumped_root(),
        help="Root directory containing dumped-wasm-files/<owner__repo>",
    )
    parser.add_argument(
        "--packages-root",
        type=Path,
        default=_default_packages_root(),
        help="Root directory containing cloned package directories (<owner__repo>)",
    )
    parser.add_argument(
        "--scan-all-package-files",
        action="store_true",
        help="Scan all .wasm/.js/.mjs/.cjs/.ts files in package root instead of only dataset files_with_wasm",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=None,
        help="Worker count for parallel scans (used with --scan-all-package-files; default: CPU count)",
    )
    parser.add_argument(
        "--progress",
        action="store_true",
        help="Print lightweight progress updates to stderr during candidate collection and scanning",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional path to write JSON report",
    )
    return parser


def main() -> int:
    parser = _build_parser()

    if len(sys.argv) == 1:
        parser.print_help(sys.stderr)
        return 2

    args = parser.parse_args()

    dataset_path = args.dataset.expanduser()
    dumped_root = args.dumped_root.expanduser()
    packages_root = args.packages_root.expanduser()

    if args.all_dumped_clients:
        report = run_all_tests(
            dataset_path=dataset_path,
            dumped_root=dumped_root,
            packages_root=packages_root,
            scan_all_package_files=args.scan_all_package_files,
            workers=args.workers,
            progress=args.progress,
        )
    else:
        report = run_test(
            dataset_path=dataset_path,
            package_name=args.package,
            dumped_root=dumped_root,
            packages_root=packages_root,
            scan_all_package_files=args.scan_all_package_files,
            workers=args.workers,
            progress=args.progress,
        )

    rendered = json.dumps(report, indent=2, sort_keys=True)
    print(rendered)

    if args.output:
        args.output.expanduser().write_text(rendered + "\n", encoding="utf-8")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())