import subprocess
import shlex
import textwrap
import os 
import json
import argparse
from pathlib import Path

DATASET_JSON = "/home/NoWaSet/scripts/node-wasm-set.json"
REPOS_DIR = "/home/NoWaSet/repos/"

def run(
    cmd,
    verbose=False,
    cwd=None,
    check=True,
    capture_output=True,
    encoding="utf-8",
    # Specify an integer number of seconds
    timeout=-1,
    **kwargs,
):
    # Copyright (c) Facebook, Inc. and its affiliates. (http://www.facebook.com)
    if verbose:
        info = "$ "
        if cwd is not None:
            info += f"cd {cwd}; "
        info += " ".join(shlex.quote(c) for c in cmd)
        if capture_output:
            info += " >& ..."
        lines = textwrap.wrap(
            info,
            break_on_hyphens=False,
            break_long_words=False,
            replace_whitespace=False,
            subsequent_indent="  ",
        )
        print(" \\\n".join(lines))
    if timeout != -1:
        cmd = ["timeout", "--signal=KILL", f"{timeout}s", *cmd]
    try:
        return subprocess.run(
            cmd,
            cwd=cwd,
            check=check,
            capture_output=capture_output,
            encoding=encoding,
            **kwargs,
        )
    except subprocess.CalledProcessError as e:
        if e.returncode == -9:
            # Error code from `timeout` command signaling it had to be killed
            raise TimeoutError("Command timed out", cmd)
        raise

def clone_repo_at_sha(path_safe_repo_full_name, ssh, commit_sha, dir):
    """
    Clone a very shallow copy of the repo with only the requested commit;
    requires Git 2.34.0 or later (or maybe earlier but we have not tested)
    
    Returns:
        Tuple of (success: bool, stage: str, stderr: str)
        - success: True if all steps completed successfully
        - stage: Which stage failed (or "success" if all succeeded)
        - stderr: Error output from failed command (or empty string if success)
    """
    repo_dir = dir+f"/{path_safe_repo_full_name}"
    if os.path.isdir(repo_dir): 
        try:
            run(['rm', '-rf', repo_dir])
        except Exception as e:
            return (False, "cleanup", str(e))

    try:
        run(["git", "init", path_safe_repo_full_name], cwd=dir)
    except Exception as e:
        result = run(["git", "init", path_safe_repo_full_name], cwd=dir, check=False)
        return (False, "clone", result.stderr if result.stderr else str(e))
    
    try:
        run(['git', 'remote', 'add', 'origin', ssh], cwd=repo_dir)
    except Exception as e:
        result = run(['git', 'remote', 'add', 'origin', ssh], cwd=repo_dir, check=False)
        return (False, "clone", result.stderr if result.stderr else str(e))
    
    try:
        run(['git', 'fetch', '--depth=1', 'origin', commit_sha.strip()], cwd=repo_dir)
    except Exception as e:
        result = run(['git', 'fetch', '--depth=1', 'origin', commit_sha.strip()], cwd=repo_dir, check=False)
        return (False, "clone", result.stderr if result.stderr else str(e))
    
    try:
        run(['git', 'checkout', '-b', 'realwasm-target-commit', commit_sha.strip()], cwd=repo_dir)
    except Exception as e:
        result = run(['git', 'checkout', '-b', 'realwasm-target-commit', commit_sha.strip()], cwd=repo_dir, check=False)
        return (False, "checkout", result.stderr if result.stderr else str(e))
    
    return (True, "success", "")


def install_and_build_repo(repo_name, package_data, repo_dir): 
    """
    Install and build a repository.
    
    Args:
        repo_name: Name of the repository
        package_data: Either npm_filter results (old format) or scripts dict (new format)
        repo_dir: Directory where the repo is located
        
    Returns:
        Tuple of (success: bool, stage: str, stderr: str)
        - success: True if all steps completed successfully
        - stage: Which stage failed: "install" or "build" (or "success" if all succeeded)
        - stderr: Error output from failed command (or empty string if success)
    """
    assert(os.path.isdir(repo_dir))

    # Support both old npm_filter format and new scripts format
    if "scripts" in package_data:
        # New format: scripts dict with install and build lists
        scripts = package_data["scripts"]
        install_script = scripts.get("install", "npm install")
        build_scripts = scripts.get("build", [])
    elif "installation" in package_data:
        # Old format: npm_filter results
        npm_filter_results = package_data
        install_possible = "installation" in npm_filter_results and "ERROR" not in npm_filter_results["installation"]
        if install_possible:
            install_script = npm_filter_results["installation"]["installer_command"]
        else:
            install_script = None
            
        build_possible = "build" in npm_filter_results and "ERROR" not in npm_filter_results["build"]
        if build_possible:
            build_scripts = npm_filter_results["build"]["build_script_list"]
        else:
            build_scripts = []
    else:
        # Fallback to defaults
        install_script = "npm install"
        build_scripts = []

    # Run the install script if it exists
    if install_script:
        # Check if this is a Yarn installation
        is_yarn = 'yarn' in install_script.lower()
        
        # If using Yarn, use flags that avoid cache corruption issues
        if is_yarn:
            # Check if yarn.lock exists to confirm it's a Yarn project
            yarn_lock = os.path.join(repo_dir, 'yarn.lock')
            if os.path.exists(yarn_lock):
                # Modify install command to use flags that avoid cache issues
                # --mutex network: Prevents concurrent yarn operations from corrupting cache
                # --network-timeout: Handle slow/flaky network
                # --check-files: Verify integrity of files in node_modules
                if install_script in ['yarn', 'yarn install']:
                    install_script = 'yarn install --mutex network --network-timeout 100000'
        
        install_result = run(shlex.split(install_script), check=False, cwd=repo_dir)        

        if repo_name == 'yisibl/resvg-js': 
            run(['npm', 'i', 'benny'], check=False, cwd=repo_dir)
                
        if install_result.returncode != 0:
            # Capture more stderr for better debugging (increase from 500 to 1000 chars)
            stderr_msg = install_result.stderr[:1000] if install_result.stderr else ""
            # Also capture some stdout as errors might be there
            stdout_msg = install_result.stdout[:500] if install_result.stdout else ""
            combined_msg = f"{stderr_msg}\n---STDOUT---\n{stdout_msg}" if stdout_msg else stderr_msg
            return (False, "install", combined_msg)

    # Run build scripts if they exist          
    if build_scripts:
        for build_script in build_scripts:
            # build_script might already have "npm run" prefix or might be just the script name
            if build_script.startswith("npm run "):
                cmd = shlex.split(build_script)
            else:
                cmd = shlex.split(build_script)
            
            build_result = run(cmd, check=False, cwd=repo_dir)
            if build_result.returncode != 0:
                return (False, "build", build_result.stderr[:500] if build_result.stderr else "")

    return (True, "success", "")  

def checkout(branch_name, commit_sha, repo_dir): 
    run(['git', 'checkout', '-b', branch_name, commit_sha.strip()], cwd=repo_dir)

def clone_checkout_install_build(package_name, package_data, output_dir=None):
    """
    Clone a repository, checkout at specific commit, install dependencies, and build.
    
    Args:
        package_name: Name of the package (e.g., "owner/repo")
        package_data: Package data from the dataset JSON containing github_metadata and scripts
        output_dir: Directory to clone repository into (default: REPOS_DIR)
        
    Returns:
        Tuple of (success: bool, repo_dir: str, stage: str, message: str)
        - success: True if all steps completed successfully
        - repo_dir: Path to repository directory (or None if clone failed)
        - stage: Which stage operation was in ("clone", "checkout", "install", "build", or "success")
        - message: Human-readable message (includes stderr excerpt on failure)
    """
    if output_dir is None:
        output_dir = REPOS_DIR
    
    # Create output directory if it doesn't exist
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    
    # Extract metadata - support both old and new format
    if "github_metadata" in package_data:
        metadata = package_data["github_metadata"]
    elif "repo_metadata" in package_data:
        metadata = package_data["repo_metadata"]
    else:
        return (False, None, "metadata", "No metadata found in package data")
    
    full_name = metadata["full_name"]
    clone_url = metadata.get("clone_url") or metadata.get("ssh_url")
    commit_sha = metadata["commit_SHA"]
    
    if not clone_url:
        return (False, None, "metadata", "No clone URL found in metadata")
    
    # Create path-safe repository name
    repo_fullname_path_safe = "__".join(full_name.split("/"))
    repo_dir = os.path.join(output_dir, repo_fullname_path_safe)
    
    try:
        # Clone repository at specific commit
        clone_success, clone_stage, clone_stderr = clone_repo_at_sha(
            path_safe_repo_full_name=repo_fullname_path_safe,
            ssh=clone_url,
            commit_sha=commit_sha,
            dir=output_dir
        )
        
        if not clone_success:
            # Truncate stderr for display - show first 200 chars
            stderr_excerpt = clone_stderr[:200] + "..." if len(clone_stderr) > 200 else clone_stderr
            return (False, repo_dir if os.path.exists(repo_dir) else None, clone_stage, 
                   f"Failed at {clone_stage}: {stderr_excerpt}")
        
        # Install and build
        install_success, install_stage, install_stderr = install_and_build_repo(
            repo_name=package_name,
            package_data=package_data,
            repo_dir=repo_dir
        )
        
        if not install_success:
            # Truncate stderr for display - show first 200 chars
            stderr_excerpt = install_stderr[:200] + "..." if len(install_stderr) > 200 else install_stderr
            return (False, repo_dir, install_stage, 
                   f"Failed at {install_stage}: {stderr_excerpt}")
        
        return (True, repo_dir, "success", "Successfully cloned, checked out, installed, and built")
        
    except Exception as e:
        return (False, repo_dir if os.path.exists(repo_dir) else None, "unknown", f"Exception: {str(e)}")



def pretty_print_number(n, max_len): 
    num_spaces = max_len-len(str(n))
    return f"{num_spaces*'0'}{n}"

def run_tests(test_scripts, repo_dir): 
    assert(os.path.isdir(repo_dir))
    test_returncodes = []
    for test in test_scripts:
        test_result = run(["npm", "run", test], check=False, cwd=repo_dir)
        test_returncodes.append(test_result.returncode)
    return test_returncodes

def clone_all_projects(): 
    run(["mkdir", "-p", REPOS_DIR])

    with open(DATASET_JSON, 'r') as f: 
        dywasmbench = json.load(f)

    total_repos = len(dywasmbench)
    max_len = len(str(total_repos))
    for (repo_num, (repo_name, repo_json)) in enumerate(dywasmbench.items()): 
        # Support both old and new format
        metadata = repo_json.get("github_metadata") or repo_json.get("repo_metadata")
        full_name = metadata["full_name"]
        repo_fullname_path_safe = "__".join(full_name.split("/"))
        print(f"({pretty_print_number(repo_num+1, max_len)}/{total_repos}): Cloning {repo_name}")
        success, stage, stderr = clone_repo_at_sha(
            path_safe_repo_full_name=repo_fullname_path_safe,
            ssh=metadata.get("clone_url") or metadata.get("ssh_url"),
            commit_sha=metadata["commit_SHA"], 
            dir=REPOS_DIR        
        )
        if not success:
            print(f"  Failed at {stage}: {stderr[:100]}")

def build_all_projects(): 
    with open(DATASET_JSON, 'r') as f: 
        dywasmbench = json.load(f)

    total_repos = len(dywasmbench)
    max_len = len(str(total_repos))
    for (repo_num, (repo_name, repo_json)) in enumerate(dywasmbench.items()): 
        # Support both old and new format
        metadata = repo_json.get("github_metadata") or repo_json.get("repo_metadata")
        full_name = metadata["full_name"]
        repo_fullname_path_safe = "__".join(full_name.split("/"))
        repo_dir = REPOS_DIR + "/" + repo_fullname_path_safe 
        print(f"({pretty_print_number(repo_num+1, max_len)}/{total_repos}): Building {repo_name}")
        success, stage, stderr = install_and_build_repo(repo_name, repo_json, repo_dir)
        if not success:
            print(f"  Failed at {stage}: {stderr[:100]}")

def run_all_repo_tests(): 
    with open(DATASET_JSON, 'r') as f: 
        dywasmbench = json.load(f)

    total_repos = len(dywasmbench)
    max_len = len(str(total_repos))
    for (repo_num, (repo_name, repo_json)) in enumerate(dywasmbench.items()): 
        full_name = repo_json["repo_metadata"]["full_name"]
        repo_fullname_path_safe = "__".join(full_name.split("/"))
        repo_dir = REPOS_DIR + "/" + repo_fullname_path_safe 
        tests_to_run = [test for test in repo_json["npm_filter"]["testing"]]
        print(f"({pretty_print_number(repo_num+1, max_len)}/{total_repos}): Running tests for {repo_name}")
        run_tests(test_scripts=tests_to_run, repo_dir=repo_dir)

def clone_and_build_all_repos(): 
    run(["mkdir", "-p", REPOS_DIR])

    with open(DATASET_JSON, 'r') as f: 
        dywasmbench = json.load(f)

    total_repos = len(dywasmbench)
    max_len = len(str(total_repos))
    for (repo_num, (repo_name, repo_json)) in enumerate(dywasmbench.items()): 
        # Support both old and new format
        metadata = repo_json.get("github_metadata") or repo_json.get("repo_metadata")
        full_name = metadata["full_name"]
        repo_fullname_path_safe = "__".join(full_name.split("/"))
        repo_dir = REPOS_DIR + "/" + repo_fullname_path_safe 
        print(f"({pretty_print_number(repo_num+1, max_len)}/{total_repos}): Cloning and building {repo_name}")
        success, stage, stderr = clone_repo_at_sha(
            path_safe_repo_full_name=repo_fullname_path_safe,
            ssh=metadata.get("clone_url") or metadata.get("ssh_url"),
            commit_sha=metadata["commit_SHA"], 
            dir=REPOS_DIR        
        )
        if not success:
            print(f"  Clone failed at {stage}: {stderr[:100]}")
            continue
        
        success, stage, stderr = install_and_build_repo(repo_name, repo_json, repo_dir)
        if not success:
            print(f"  Build failed at {stage}: {stderr[:100]}")
        
if __name__ == "__main__":

    parser = argparse.ArgumentParser(description="Utility script for DyWasmBench")
    parser.add_argument("--clone-build-all", action='store_true', required=False, help="Clone and build all repos in DyWasmBench.")    
    parser.add_argument("--clone-all", action='store_true', required=False, help="Clone all repos in DyWasmBench.")    
    parser.add_argument("--build-all", action='store_true', required=False, help="Build all repos in DyWasmBench.")
    parser.add_argument("--test-all", action='store_true', required=False, help="Run test scripts of all repos in DyWasmBench.")
    
    args = parser.parse_args()

    CLONE_BUILD = args.clone_build_all    
    CLONE = args.clone_all
    BUILD = args.build_all
    TEST = args.test_all 

    if CLONE_BUILD: clone_and_build_all_repos()
    if CLONE: clone_all_projects()
    if BUILD: build_all_projects()
    if TEST: run_all_repo_tests()