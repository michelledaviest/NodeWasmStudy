#!/usr/bin/env python3
"""
Adds "js_wrapper" to each wasm module entry in "wasm_module_details" in
dataset/node-wasm-set.json.

Rules:
  - Package not installed in NodeWasmPackages/: skip entirely (don't add key).
  - static_paths is empty/null: js_wrapper = null (dynamic load, no static wrapper).
  - static_path ends with .wasm: search same directory in NodeWasmPackages for a JS
    file that (a) contains the .wasm filename as a string, and (b) has a
    WebAssembly.instantiate / instantiateStreaming / Instance call.
  - static_path ends with .js/.mjs/.cjs/etc.: the wrapper IS that file.

js_wrapper is stored as an object (or null):
  {
    "path":        [<relative path>, ...],   # all unique wrapper paths found
    "is_minified": <bool>,                   # based on first path: any line > 500 chars
    "map_file":    <null | "inline" | path>, # null if not minified or no map found;
                                             # "inline" for data: URI source maps;
                                             # relative path for external .map files
    "typescript":  <bool>                    # true if .d.ts with same stem exists in
                                             # same dir, OR file has JSDoc type annotations
  }
"""

import json
import os
import re

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DATASET_PATH = os.path.join(REPO_ROOT, "dataset/node-wasm-set.json")
PACKAGES_DIR = os.path.expanduser("~/NodeWasmPackages")

JS_EXTENSIONS = {".js", ".mjs", ".cjs"}
WASM_INSTANTIATE_RE = re.compile(
    r"WebAssembly\.(instantiate|instantiateStreaming|Instance)\b"
)
SOURCE_MAP_RE = re.compile(
    r"//# sourceMappingURL=(.+?)[\s]*$", re.MULTILINE
)
JSDOC_TYPE_RE = re.compile(
    r"@type\s*\{|@param\s*\{|@returns?\s*\{"
)
MINIFIED_LINE_THRESHOLD = 500


# ---------------------------------------------------------------------------
# Finding the wrapper path(s)
# ---------------------------------------------------------------------------

def find_js_wrapper_for_wasm(pkg_dir, static_path):
    """
    Given a path like 'node_modules/foo/dist/foo.wasm', look in the same
    directory under pkg_dir for a JS file that references the .wasm filename
    and contains a WebAssembly instantiation call.

    Returns the relative path (same style as static_path) or None.
    """
    wasm_filename = os.path.basename(static_path)
    wasm_stem = os.path.splitext(wasm_filename)[0]
    search_dir = os.path.join(pkg_dir, os.path.dirname(static_path))

    if not os.path.isdir(search_dir):
        return None

    for entry in os.listdir(search_dir):
        if os.path.splitext(entry)[1].lower() not in JS_EXTENSIONS:
            continue
        candidate = os.path.join(search_dir, entry)
        try:
            with open(candidate, encoding="utf-8", errors="replace") as fh:
                content = fh.read()
        except OSError:
            continue

        if wasm_filename not in content and wasm_stem not in content:
            continue
        if not WASM_INSTANTIATE_RE.search(content):
            continue

        return os.path.join(os.path.dirname(static_path), entry)

    return None


def collect_wrapper_paths(pkg_name, static_paths):
    """Returns a list of unique wrapper paths, or None if none found."""
    if not static_paths:
        return None

    pkg_dir = os.path.join(PACKAGES_DIR, pkg_name.replace("/", "__"))
    wrappers = []
    seen = set()

    for sp in static_paths:
        if os.path.splitext(sp)[1].lower() in JS_EXTENSIONS:
            if sp not in seen:
                wrappers.append(sp)
                seen.add(sp)
        else:
            wrapper = find_js_wrapper_for_wasm(pkg_dir, sp)
            if wrapper and wrapper not in seen:
                wrappers.append(wrapper)
                seen.add(wrapper)

    return wrappers if wrappers else None


# ---------------------------------------------------------------------------
# Wrapper metadata (checked against first path only)
# ---------------------------------------------------------------------------

def read_wrapper_content(pkg_name, wrapper_path):
    """Read and return the content of the first wrapper file, or None on error."""
    abs_path = os.path.join(PACKAGES_DIR, pkg_name.replace("/", "__"), wrapper_path)
    try:
        with open(abs_path, encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return None


def check_minified(content):
    """True if any line exceeds MINIFIED_LINE_THRESHOLD characters."""
    return any(len(line) > MINIFIED_LINE_THRESHOLD for line in content.splitlines())


def check_map_file(content, pkg_name, wrapper_path):
    """
    Returns:
      None       — not minified, or minified but no sourceMappingURL found
      "inline"   — sourceMappingURL is a data: URI (map embedded in file)
      <str>      — relative path (same format as static_paths) to external .map file
    """
    match = SOURCE_MAP_RE.search(content)
    if not match:
        return None

    url = match.group(1).strip()
    if url.startswith("data:"):
        return "inline"

    # External reference: resolve relative to the wrapper's directory
    wrapper_dir = os.path.dirname(wrapper_path)
    map_rel_path = os.path.normpath(os.path.join(wrapper_dir, url))
    abs_map = os.path.join(PACKAGES_DIR, pkg_name.replace("/", "__"), map_rel_path)
    if os.path.isfile(abs_map):
        return map_rel_path

    return None


def check_typescript(content, pkg_name, wrapper_path):
    """
    True if:
      - A .d.ts file with the same stem exists in the same directory, OR
      - The wrapper file itself contains JSDoc type annotations.
    """
    stem = os.path.splitext(os.path.basename(wrapper_path))[0]
    wrapper_dir = os.path.dirname(wrapper_path)
    dts_rel = os.path.join(wrapper_dir, stem + ".d.ts")
    abs_dts = os.path.join(PACKAGES_DIR, pkg_name.replace("/", "__"), dts_rel)
    if os.path.isfile(abs_dts):
        return True

    return bool(JSDOC_TYPE_RE.search(content))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def build_js_wrapper(pkg_name, static_paths):
    """
    Returns the full js_wrapper object, or None if no wrapper paths found
    (including the dynamic / empty static_paths case).
    """
    paths = collect_wrapper_paths(pkg_name, static_paths)
    if paths is None:
        return None

    content = read_wrapper_content(pkg_name, paths[0])
    if content is None:
        return {"path": paths, "is_minified": None, "map_file": None, "typescript": None}

    minified = check_minified(content)
    map_file = check_map_file(content, pkg_name, paths[0]) if minified else None
    typescript = check_typescript(content, pkg_name, paths[0])

    return {
        "path": paths,
        "is_minified": minified,
        "map_file": map_file,
        "typescript": typescript,
    }


def main():
    with open(DATASET_PATH) as f:
        dataset = json.load(f)

    installed = set(os.listdir(PACKAGES_DIR))

    stats = {"skipped_not_installed": 0, "null_dynamic": 0, "found": 0, "not_found": 0}

    for pkg_name, pkg_data in dataset.items():
        dir_name = pkg_name.replace("/", "__")
        details = pkg_data.get("wasm_module_details", {})

        if not details:
            continue

        if dir_name not in installed:
            stats["skipped_not_installed"] += len(details)
            continue

        for wasm_hash, module_info in details.items():
            static_paths = module_info.get("static_paths") or []
            wrapper = build_js_wrapper(pkg_name, static_paths)

            module_info["js_wrapper"] = wrapper

            if wrapper is None:
                if not static_paths:
                    stats["null_dynamic"] += 1
                else:
                    stats["not_found"] += 1
            else:
                stats["found"] += 1

    with open(DATASET_PATH, "w") as f:
        json.dump(dataset, f, indent=2)

    print("Done.")
    print(f"  js_wrapper found:                    {stats['found']}")
    print(f"  js_wrapper null (dynamic):           {stats['null_dynamic']}")
    print(f"  js_wrapper null (not found in dir):  {stats['not_found']}")
    print(f"  modules skipped (pkg not installed): {stats['skipped_not_installed']}")


if __name__ == "__main__":
    main()
