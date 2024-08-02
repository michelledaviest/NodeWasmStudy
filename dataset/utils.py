import subprocess
import shlex
import textwrap
import os 
import json
import argparse

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
    # Clone a very shallow copy of the repo with only the requested commit;
    # requires Git 2.34.0 or later (or maybe earlier but we have not tested)
    
    repo_dir = dir+f"/{path_safe_repo_full_name}"
    if os.path.isdir(repo_dir): 
        run(['rm', '-rf', repo_dir])

    run(["git", "init", path_safe_repo_full_name], cwd=dir)    
    run(['git', 'remote', 'add', 'origin', ssh], cwd=repo_dir)
    run(['git', 'fetch', '--depth=1', 'origin', commit_sha.strip()], cwd=repo_dir)
    run(['git', 'checkout', '-b', 'realwasm-target-commit', commit_sha.strip()], cwd=repo_dir)

def get_env_with_node_with_flags():
    my_env = os.environ.copy()
    node_experimental_vm_modules = f"{os.getcwd()}/node-experimental-vm-modules"
    my_env["PATH"] = f"{node_experimental_vm_modules}:{my_env['PATH']}"    
    return my_env

def install_and_build_repo(repo_name, npm_filter_results, repo_dir): 
    assert(os.path.isdir(repo_dir))

    # Run the install and build scripts, if they exist 
    install_possible = "installation" in npm_filter_results.keys() and "ERROR" not in npm_filter_results["installation"].keys()
    if install_possible: 
        install_script = npm_filter_results["installation"]["installer_command"]
        install_result = run(shlex.split(install_script), check=False, cwd=repo_dir, env=get_env_with_node_with_flags())        

        if repo_name == 'yisibl/resvg-js': 
            run(['npm', 'i', 'benny'], check=False, cwd=repo_dir, env=get_env_with_node_with_flags())
                
        if install_result.returncode != 0:
            return False

    build_possible = "build" in npm_filter_results.keys() and "ERROR" not in npm_filter_results["build"].keys()              
    if build_possible:
        build_scripts = npm_filter_results["build"]["build_script_list"]
        for build_script in build_scripts:
            build_result = run(
                            shlex.split("npm run "+ build_script), 
                            check=False,
                            cwd=repo_dir, 
                            env=get_env_with_node_with_flags()
                        )
            if build_result.returncode != 0:
                return False 

    return True  

def checkout(branch_name, commit_sha, repo_dir): 
    run(['git', 'checkout', '-b', branch_name, commit_sha.strip()], cwd=repo_dir)

def pretty_print_number(n, max_len): 
    num_spaces = max_len-len(str(n))
    return f"{num_spaces*'0'}{n}"

def run_tests(test_scripts, repo_dir): 
    assert(os.path.isdir(repo_dir))
    test_returncodes = []
    for test in test_scripts:
        test_result = run(["npm", "run", test], check=False, cwd=repo_dir, env=get_env_with_node_with_flags())
        test_returncodes.append(test_result.returncode)
    return test_returncodes

def clone_all_projects(): 
    run(["mkdir", "-p", REPOS_DIR])

    with open(DATASET_JSON, 'r') as f: 
        dywasmbench = json.load(f)

    total_repos = len(dywasmbench)
    max_len = len(str(total_repos))
    for (repo_num, (repo_name, repo_json)) in enumerate(dywasmbench.items()): 
        full_name = repo_json["repo_metadata"]["full_name"]
        repo_fullname_path_safe = "__".join(full_name.split("/"))
        print(f"({pretty_print_number(repo_num+1, max_len)}/{total_repos}): Cloning {repo_name}")
        clone_repo_at_sha(
            path_safe_repo_full_name=repo_fullname_path_safe,
            ssh=repo_json["repo_metadata"]["clone_url"],
            commit_sha=repo_json["repo_metadata"]["commit_SHA"], 
            dir=REPOS_DIR        
        )

def build_all_projects(): 
    with open(DATASET_JSON, 'r') as f: 
        dywasmbench = json.load(f)

    total_repos = len(dywasmbench)
    max_len = len(str(total_repos))
    for (repo_num, (repo_name, repo_json)) in enumerate(dywasmbench.items()): 
        full_name = repo_json["repo_metadata"]["full_name"]
        repo_fullname_path_safe = "__".join(full_name.split("/"))
        repo_dir = REPOS_DIR + "/" + repo_fullname_path_safe 
        print(f"({pretty_print_number(repo_num+1, max_len)}/{total_repos}): Building {repo_name}")
        install_and_build_repo(repo_name, repo_json["npm_filter"], repo_dir)

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
        full_name = repo_json["repo_metadata"]["full_name"]
        repo_fullname_path_safe = "__".join(full_name.split("/"))
        repo_dir = REPOS_DIR + "/" + repo_fullname_path_safe 
        print(f"({pretty_print_number(repo_num+1, max_len)}/{total_repos}): Cloning and building {repo_name}")
        clone_repo_at_sha(
            path_safe_repo_full_name=repo_fullname_path_safe,
            ssh=repo_json["repo_metadata"]["clone_url"],
            commit_sha=repo_json["repo_metadata"]["commit_SHA"], 
            dir=REPOS_DIR        
        )
        install_and_build_repo(repo_name, repo_json["npm_filter"], repo_dir)
        
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