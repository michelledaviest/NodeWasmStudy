#!/usr/bin/env python3

import argparse
import json
import multiprocessing
import pathlib
import shlex

from utils import run, clone_repo_at_sha, install_and_build_repo, get_env_with_node_with_flags, rm_rf_repo, get_realwasm_log, checkout, hash_wasm_file
from utils import REALWASM_JSON, TESTING_REPO, DEP_ANLYSIS_JSON, IGNORED_REPOS

TRANSFORM_SCRIPT = './dynamic-analysis/transform-dir.sh'
UNTRANSFORM_SCRIPT = './dynamic-analysis/untransform-dir.sh'

def instrument_js_files(path): 
    instrument_result = run([TRANSFORM_SCRIPT, path], check=False) 
    return instrument_result.returncode == 0

def uninstrument_js_files(path, cwd=None): 
    run([UNTRANSFORM_SCRIPT, path])

def get_test_returncodes(tests, dir): 
    test_returncodes = []
    for test in tests:
        test_result = run(["npm", "run", test], check=False, cwd=dir, env=get_env_with_node_with_flags())
        test_returncodes.append(test_result.returncode)
    return test_returncodes

def transfer_dumped_wasm(realwasmlog, repo_full_name_path_safe): 
    dump_wasm_in_dir = f"{DUMPED_WASM_FILES}/{repo_full_name_path_safe}"
    todo_to_hash = {}
    run(['mkdir', '-p', dump_wasm_in_dir])
    for line in realwasmlog:
        if "DumpCompiledWasm" in line: 
            # Example: "RealWasmLog,DumpCompiledWasm,/home/RealWasm/docker-tmp/realwasm-module-a213b49905f0fc26138071636f8b448b3273badb4c2e4b0e2b56becef29706da.wasm"            
            dumped_wasm_file = line.split("__,__")[2].strip()
            if "TODO" in dumped_wasm_file:
                file_hash = hash_wasm_file(dumped_wasm_file)
                todo_to_hash[pathlib.Path(dumped_wasm_file).stem[16:]] = file_hash
                new_file_name = f"/home/RealWasm/docker-tmp/realwasm-module-{file_hash}.wasm"
                run(['cp', dumped_wasm_file, new_file_name], check=False)
                dumped_wasm_file = new_file_name
            run(['cp', dumped_wasm_file, dump_wasm_in_dir], check=False)
    return replace_TODO_wasm_refs_with_hashes(realwasmlog, todo_to_hash)

def replace_TODO_wasm_refs_with_hashes(realwasmlog, todo_to_hash_hashmap):
    new_log = []
    for line in realwasmlog:
        if "TODO" in line: 
            new_line = []
            for line_br in line.split("__,__"): 
                if "TODO" in line_br: 
                    for todo in todo_to_hash_hashmap:
                        if todo in line_br: 
                            line_br = line_br.replace(todo, todo_to_hash_hashmap[todo])
                new_line.append(line_br)
            new_line = "__,__".join(new_line)
        else: 
            new_line = line

        if LOG_STACK_TRACES:
            new_log.append(new_line)
        else: 
            new_log.append("__,__".join(new_line.split("__,__")[:-1]))
        
    return new_log 

def run_tests(repo_full_name_path_safe, tests, dir, dynamic_log, actual_test_returncodes): 
    tests_success = True 
    for test_num, test in enumerate(tests):
        test_result = run(["npm", "run", test], check=False, cwd=dir, env=get_env_with_node_with_flags())

        realwasmlog, stderr = get_realwasm_log(test_result)
        realwasmlog = transfer_dumped_wasm(realwasmlog, repo_full_name_path_safe) 

        is_error = test_result.returncode != actual_test_returncodes[test_num]
        dynamic_log[test] = {
            "log"   : realwasmlog,
            # "error" : is_error, 
            # "stderr": stderr
        }
        tests_success = tests_success and is_error is False

    return tests_success

def get_dynamic_results(repo):    
    repo_name = repo["repo_metadata"]["name"]
    repo_fullname = repo["repo_metadata"]["full_name"]
    repo_fullname_path_safe = "__".join(repo_fullname.split("/"))
    repo_dir = TESTING_REPO + "/" + repo_fullname_path_safe 
    tests_to_run = [test for test in repo["npm_filter"]["testing"]]

    transformation_result = [] # Save npm package name, if the transformation succeeded and if the tests passes
    
    # We are going to create a directory that is the same name as the repo 
    # Log files for each NPM package (or self) being tested will be in this directory
    run(["mkdir", "-p", str(EVALUATION)])
    dynamic_log_repo = f"{EVALUATION}/dynamic-results/{repo_fullname_path_safe}" 
    run(['mkdir', '-p', dynamic_log_repo])

    self_log_file = f"{dynamic_log_repo}/self.json"
    self_log = {}

    # First we will install, build and run tests to get the return codes of the tests
    install_build_success, build_realwasmlog = install_and_build_repo(repo_name=repo_name, npm_filter_results=repo["npm_filter"], repo_dir=repo_dir)
    if not install_build_success:
        print(f"FAILURE: {repo_fullname} Failed to Install/Build Successfully (without instrumentation).")
        return (False, None)
    test_returncodes = get_test_returncodes(tests=tests_to_run, dir=repo_dir)    

    # Delete node_modules and checkout so that repo is in intial cloned state 
    run(["rm", "-rf", "node_modules"], check=False, cwd=repo_dir)
    checkout(branch_name="self_logs", commit_sha=repo["repo_metadata"]["commit_SHA"], repo_dir=repo_dir)

    # Next we want to check that the repo itself exercises wasm (without any of the npm packages)
    # Run transform on the repo without installing    
    instrument_success = instrument_js_files(path=f"./{TESTING_REPO}/{repo_fullname_path_safe}")

    # Install, build and capture log in "build" 
    # Run tests and capture log in "self"
    install_build_success, build_realwasmlog = install_and_build_repo(repo_name=repo_name, npm_filter_results=repo["npm_filter"], repo_dir=repo_dir)

    # NOTE: A lot of these errors are because of repositories have linters in their build systems. 
    # We just don't have self reports for these repos. 
    #if not install_build_success:
        #print(f"FAILURE: {repo_fullname} Failed to Install/Build Successfully after instrumentation.")
        #return (False, None)

    if install_build_success: 
        build_realwasmlog = transfer_dumped_wasm(build_realwasmlog, repo_fullname_path_safe) 
        self_log["build"] = {
            "log": build_realwasmlog, 
            # "error": False, 
            # "stderr": []
        }
    
        tests_success = run_tests(
            repo_full_name_path_safe=repo_fullname_path_safe, 
            tests=tests_to_run, 
            dir=repo_dir, 
            dynamic_log=self_log, 
            actual_test_returncodes=test_returncodes
        )
        transformation_result.append(("self", instrument_success, tests_success))

        # Save self log 
        with open(self_log_file, 'w+') as self_f: 
            json.dump({
                "log": self_log, 
            }, self_f, ensure_ascii=False, indent=2)

    # Delete node_modules and git checkout so that repo is in intial cloned state
    run(["rm", "-rf", "node_modules"], check=False, cwd=repo_dir)
    uninstrument_js_files(path=f"./{TESTING_REPO}/{repo_fullname_path_safe}")
    checkout(branch_name="package_logs", commit_sha=repo["repo_metadata"]["commit_SHA"], repo_dir=repo_dir)

    # Now we instrument the neccessary npm packages and get logs for each of them.  

    # Install and build repo (should always succeed)  
    install_build_success, _ = install_and_build_repo(repo_name=repo_name, npm_filter_results=repo["npm_filter"], repo_dir=repo_dir)
    if not install_build_success: 
        print(f"FAILURE: {repo_fullname} Failed to Install/Build Successfully after untransforming.")
        return (False, None)

    # Get packages to instrument from dep analysis 
    with open(DEP_ANLYSIS_JSON, 'r') as f: 
        dep_analysis_results = json.load(f)
    clients = dep_analysis_results[repo_fullname]["client_for"]
    files_with_wasm = dep_analysis_results[repo_fullname]["files_with_wasm"]
    paths_to_npm_packages = {} 
    for path in files_with_wasm: 
        for client in clients: 
            if client in path: 
                paths_to_npm_packages[client] = path.split(client)[0]+client
        

    # Instrument each package and log results 
    for i, npm_package in enumerate(paths_to_npm_packages):
        
        path_to_npm_package = paths_to_npm_packages[npm_package]
        
        npm_package_path_safe = "__".join(npm_package.split("/")) 
        npm_package_log_file = f"{dynamic_log_repo}/{npm_package_path_safe}.json"
        package_log = {}
        
        uninstrument_js_files(path=path_to_npm_package)
    
        # Run transform.sh on the ./node_modules/{library_name(s)}
        instrument_success = instrument_js_files(path=path_to_npm_package)

        # Run the test script(s) that touch WebAssembly and save in output_dir/json_file
        tests_success = run_tests(
            repo_full_name_path_safe=repo_fullname_path_safe, 
            tests=tests_to_run, 
            dir=repo_dir, 
            dynamic_log=package_log, 
            actual_test_returncodes=test_returncodes
        )
        transformation_result.append((npm_package, instrument_success, tests_success))

        # Dump log in JSON file 
        with open(npm_package_log_file, "w+") as outfile:
            json.dump({ 
                "log": package_log, 
            }, outfile, ensure_ascii=False, indent=2)

    print(f"SUCCESS: {repo_fullname} results dumped in {EVALUATION} repo.")

    rm_rf_repo(repo_dir)
    return (install_build_success, transformation_result)

def bool_to_tick_cross(val):
    return "✓" if val else "x"

def get_dynamic_log(repo): 

    with open(REALWASM_JSON, 'r') as results_input:
        dataset = json.load(results_input)

    path_safe_repo_full_name = "__".join(dataset[repo]["repo_metadata"]["full_name"].split("/")) 

    clone_repo_at_sha(
        path_safe_repo_full_name=path_safe_repo_full_name,
        ssh=dataset[repo]["repo_metadata"]["clone_url"],
        commit_sha=dataset[repo]["repo_metadata"]["commit_SHA"], 
        dir=TESTING_REPO
    )

    (install_build_success, transformation_result) = get_dynamic_results(dataset[repo])

    npm_packages, transform_results, tests_results = [], [], []
    if install_build_success: 
        for res in transformation_result: 
            npm_package, transform_succeeded, tests_succeeded = res
            npm_packages.append(npm_package)
            transform_results.append(transform_succeeded)
            tests_results.append(tests_succeeded)

    # This needs to happen inside this function to keep last_output_per_process
    # from exceeding the limit.
    
    return (
        repo, 
        install_build_success,
        npm_packages, 
        transform_results, 
        tests_results
    )


def get_dynamic_log_wrapper(repo):
    # Catch exceptions and remove the repo from last_output_per_process if it's
    # there. This stops the terminal from getting clogged up with failed repos.
    try:
        return get_dynamic_log(repo)
    except Exception as e:
        print(f"{repo} raised Exception: {e}")
        return (repo, False, [], [], [])

def get_realwasm_results():
    with open(REALWASM_JSON, 'r') as results_input:
        dataset = json.load(results_input)

    total_repos = 0 
    npm_packages_transformed = []
    total_transforms_success, total_transforms_fail = 0, 0 
    total_tests_success, total_tests_fail = 0, 0 

    repos_to_process = []
    for repo in dataset: 
        repo_full_name = dataset[repo]["repo_metadata"]["full_name"]
        if repo_full_name in SUCCESS_REPOS: 
            continue
        if repo_full_name in IGNORED_REPOS: 
            continue

        repos_to_process.append(repo)

    print(f"Processing {len(repos_to_process)} repositories. {len(SUCCESS_REPOS)} already processed.")
    num_procs = 25  # multiprocessing.cpu_count()
    num_lines = min(len(repos_to_process), num_procs)
    with multiprocessing.Pool(num_lines) as pool:
        for result in pool.imap(get_dynamic_log_wrapper, repos_to_process, chunksize=1):
            (repo, install_build_success, npm_packages, transform_result, tests_result) = result
            total_repos += 1
            npm_packages_transformed.extend(npm_packages)
            for res in transform_result:
                if res: 
                    total_transforms_success +=1
                else: 
                    total_transforms_fail += 1
            for res in tests_result:
                if res: 
                    total_tests_success +=1
                else: 
                    total_tests_fail += 1

    print()
    print("Summary:")
    print(f"  {total_repos} repositories analyzed.")
    print(f"  {len(npm_packages_transformed)} NPM packages transformed.")
    print(f"  {len(set(npm_packages_transformed))} unique NPM packages transformed.")
    print(f"  {total_transforms_success} transformations succeeded.")
    print(f"  {total_transforms_fail} transformations failed.")
    print(f"  {total_tests_success} tests succeeded after transformation.")
    print(f"  {total_tests_fail} tests failed after transformation.")


def get_results_for_single_repo(repo_name): 
    (_repo, install_build_success, npm_packages, transform_result, tests_result) = get_dynamic_log(repo_name)


if __name__ == "__main__":

    global SUCCESS_REPOS
    SUCCESS_REPOS = []

    parser = argparse.ArgumentParser(description="Collect dynamic results")
    parser.add_argument("--output-dir", type=pathlib.Path, required=True, help="Output directory")
    parser.add_argument("--single-repo", required=False, help="Run dynamic analysis on a single repo")
    parser.add_argument("--dataset", action='store_true', required=False, help="Run dynamic analysis on the entire dataset")
    parser.add_argument("--stack-traces", action='store_true', required=False, help="Log stack traces in dynamic log")
    
    global EVALUATION
    global DUMPED_WASM_FILES
    global LOG_STACK_TRACES

    args = parser.parse_args()
    EVALUATION = args.output_dir
    SINGLE_REPO = args.single_repo
    ENTIRE_DATASET = args.dataset
    LOG_STACK_TRACES = args.stack_traces 
    if LOG_STACK_TRACES:
        print(f"Logging stack trace for dynamic logs. WARNING: This will greatly increase the size of your dynamic logs and should only be used for debugging.")

    DUMPED_WASM_FILES = f"{EVALUATION}/dumped-wasm-files"
    try:
        run(["mkdir", "-p", TESTING_REPO])
        run(["mkdir", "-p", DUMPED_WASM_FILES])
        if SINGLE_REPO is not None: 
            print(f"Analyzing {SINGLE_REPO}...")
            get_results_for_single_repo(SINGLE_REPO)
        if ENTIRE_DATASET:
            get_realwasm_results()
    finally:
        run(shlex.split(f"rm -rf {TESTING_REPO}/*"))
