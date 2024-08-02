from collections import Counter
import json 
import os 
import re 
import multiprocessing

from utils import run, clone_repo_at_sha, install_and_build_repo, rm_rf_repo, DEP_ANLYSIS_JSON, TESTING_REPO
from utils import REALWASM_JSON, DYNAMIC_RESULTS, DUMPED_WASM_FILES, INSTANTIATION_JSON

DEBUGGING_DIR = "./../data/debugging"
REPOS_WITH_ERROR = f"{DEBUGGING_DIR}/repos-with-error.json"
REPOS_WITH_DUMP_BUGS = f"{DEBUGGING_DIR}/repos-with-dump-bugs.json"
MYSTERY_WASM = f"{DEBUGGING_DIR}/mystery-wasm.json"
PACKAGE_STATIC_INSTS = f"{DEBUGGING_DIR}/package-static-insts.json"

def get_repo_error_stats(repo_results_dir):

    repos_with_error = {}
    repos_with_dump_bugs = {}
    mystery_wasm_files = {}

    repo_first_name, repo_last_name = repo_results_dir.split("__")
    client_name = f"{repo_first_name}/{repo_last_name}"
    
    for package_log in os.listdir(f"{DYNAMIC_RESULTS}/{repo_results_dir}"):

        package_name = "/".join(package_log.replace(".json", "").split("__"))
        package_log_file = f"{DYNAMIC_RESULTS}/{repo_results_dir}/{package_log}"
        repo_name_path_safe = client_name.replace("/", "__")

        with open(package_log_file, 'r') as f: 
            package_log_json = json.load(f)                
        
        for test in package_log_json["log"]:
            
            if test == "build": 
                build_log = [] 
                for log in package_log_json["log"][test]:
                    if isinstance(log, list): 
                        build_log.extend([log_line for log_line in build_log])
                    else:
                        build_log.append(log)
                package_log_json["log"][test] = {
                    "log": build_log,
                    "error": False, 
                    "stderr": []
                }
                
            # Repos with __realwasm errors 
            # Ignoring linter errors 
            # Ignoring errors made by __realwasm_paper__log
            if "lint" not in test: 
                for line in package_log_json["log"][test]["stderr"]:
                    if "__realwasm_paper__log" in line: 
                        continue
                    if "__realwasm" in line: 
                        if client_name not in repos_with_error: 
                            repos_with_error[client_name] = {}
                        if package_name not in repos_with_error[client_name]: 
                            repos_with_error[client_name][package_name] = []
                        repos_with_error[client_name][package_name].append(test)
                        break
            
            for line in package_log_json["log"][test]["log"]: 

                try: 
                    if "__,__" in line: line_split = line.split("__,__")
                    else: line_split = line.split(",") # FIXME: Remove 
                except: 
                    print(f"In client {client_name}, package {package_name}, test {test}, could not split {line}")

                try: 
                    if "__,__" in line: realwasm_log_type = line_split[1]
                    else: realwasm_log_type = line_split[2] # FIXME: Remove 
                except: 
                    print(f"Could not find realwasm_log_type for {line} for client {client_name}, package {package_name}, test {test}")                        
                    continue

                if realwasm_log_type == "WebAssemblyInstantiateWithHash": 
                    log_index = line_split.index("WebAssemblyInstantiateWithHash")
                    wasm_hash = line_split[log_index+1]
                    # Dumping Wasm Hash failed bug 
                    if wasm_hash == "":
                        if client_name not in repos_with_dump_bugs: 
                            repos_with_dump_bugs[client_name] = []     
                        repos_with_dump_bugs[client_name].append(test)

                    wasm_hash_file = f"{DUMPED_WASM_FILES}/{repo_name_path_safe}/realwasm-module-{wasm_hash}.wasm"
                    if not os.path.isfile(wasm_hash_file): 
                        if client_name not in mystery_wasm_files:
                            mystery_wasm_files[client_name] = {}
                        if wasm_hash not in mystery_wasm_files[client_name]:
                            mystery_wasm_files[client_name][wasm_hash] = []
                        if package_log not in mystery_wasm_files[client_name][wasm_hash]: 
                            mystery_wasm_files[client_name][wasm_hash].append(package_log)
    
    return (repos_with_error, repos_with_dump_bugs, mystery_wasm_files)

def get_error_stats(): 

    repos_with_error = {}
    repos_with_dump_bugs = {}
    mystery_wasm_files = {}

    dynamic_results = os.listdir(DYNAMIC_RESULTS)

    num_procs = 25  # multiprocessing.cpu_count()
    num_lines = min(len(dynamic_results), num_procs)    
    with multiprocessing.Pool(num_lines) as pool:
        for result in pool.imap(get_repo_error_stats, dynamic_results, chunksize=1):
            (single_repos_with_error, single_repos_with_dump_bugs, single_mystery_wasm_files) = result 
            repos_with_error = {**repos_with_error, **single_repos_with_error}
            repos_with_dump_bugs = {**repos_with_dump_bugs, **single_repos_with_dump_bugs}
            mystery_wasm_files = {**mystery_wasm_files, **single_mystery_wasm_files}

    print(f"{len(repos_with_error.keys())} repositories with __realwasm errors. Ignoring lint errors and logging errors.")
    with open(REPOS_WITH_ERROR, 'w+') as f: 
        json.dump(repos_with_error, f, ensure_ascii=False, indent=2)

    print(f"{len(repos_with_dump_bugs.keys())} repositories with empty wasm hash dumps.")
    with open(REPOS_WITH_DUMP_BUGS, 'w+') as f: 
        json.dump(repos_with_dump_bugs, f, ensure_ascii=False, indent=2)

    mystery_wasm_hashes = set([wasm_hash 
        for _repo, wasm_hashes in mystery_wasm_files.items() 
        for wasm_hash in list(wasm_hashes.keys()) 
        if wasm_hash != "" and wasm_hash != "TODO"])
    print(f"{len(mystery_wasm_files.keys())} repositories with mystery wasm hashes (aka, hashes that have been interoperated with but whose dump cannot be found).")
    print(f"{len(mystery_wasm_hashes)} unique wasm_hashes are mysteries.")
    with open(MYSTERY_WASM, 'w+') as f: 
        json.dump(mystery_wasm_files, f, ensure_ascii=False, indent=2)
    
def no_static_wasm_investigation(): 
    with open(DEP_ANLYSIS_JSON, 'r') as f: 
        dep_analysis_results = json.load(f)

    no_static_wasm_repos = []
    for repo in dep_analysis_results: 
        if "unique_wasm_counts" not in dep_analysis_results[repo]: 
            continue
        if sum(dep_analysis_results[repo]["unique_wasm_counts"].values()) == 0: 
            no_static_wasm_repos.append(repo)

    print(f"{len(no_static_wasm_repos)} repositories do not have statically reported WebAssembly.")
    
    dumped_wasm_files = os.listdir(DUMPED_WASM_FILES)    
    no_wasm_dump = 0
    wasm_dump = 0
    dumped_wasm_counter = Counter()
    for repo_dir in dumped_wasm_files: 
        repo_name = repo_dir.replace("__", "/")         
        if repo_name in no_static_wasm_repos: 
            repo_dumped_wasm = os.listdir(f"./../data/dumped-wasm-files/{repo_dir}")
            if len(repo_dumped_wasm) == 0: 
                no_wasm_dump += 1
            else: 
                wasm_dump += 1
                #if len([1 for x in repo_dumped_wasm if "cd48aefa974e9fc21adec14ef0c73f0ad501b598078b12568ed129c320318154" in x]):
                #    print(repo_name)
                dumped_wasm_counter.update(repo_dumped_wasm)
    print(f"{no_wasm_dump}/{len(no_static_wasm_repos)} repos have no dynamic dump of WebAssembly.")
    print(f"{wasm_dump}/{len(no_static_wasm_repos)} repos have a dynamic dump of WebAssembly.")
    print("Dumped Wasm files counter:")
    for key, value in dumped_wasm_counter.most_common()[:10]: 
        print(f" {key}:{value}")
    # llhttp appears 6 times  
    # realwasm-module-0e6513d04dfe27e7e3ac61678b209ae90c62aa8668fb98ac3c611a64307ff21b.wasm:2
    # ./../data/dumped-wasm-files/CesiumGS__gltf-pipeline/realwasm-module-0e6513d04dfe27e7e3ac61678b209ae90c62aa8668fb98ac3c611a64307ff21b.wasm

def no_static_wasm_check_dynamic_logs(): 
    with open(DEP_ANLYSIS_JSON, 'r') as f: 
        dep_analysis_results = json.load(f)

    no_static_wasm_repos = []
    for repo in dep_analysis_results: 
        if "unique_wasm_counts" not in dep_analysis_results[repo]: 
            continue
        if sum(dep_analysis_results[repo]["unique_wasm_counts"].values()) == 0: 
            no_static_wasm_repos.append(repo)

    num_node_internal_inst = 0  
    node_internal_funcs = Counter() 
    num_wasm_inst = 0 

    for repo in no_static_wasm_repos: 
        repo_first_name, repo_last_name = repo.split("/")
        repo_name_path_safe = f"{repo_first_name}__{repo_last_name}"
        package_logs = os.listdir(f"{DYNAMIC_RESULTS}/{repo_name_path_safe}")    

        for package_log in package_logs:
            package_name = "/".join(package_log.replace(".json", "").split("__"))
            package_log_file = f"{DYNAMIC_RESULTS}/{repo_name_path_safe}/{package_log}"
            with open(package_log_file, 'r') as f: 
                package_log_json = json.load(f)
            
                for test in package_log_json["log"]:
                
                    # FIXME: 
                    if test == "build": 
                        build_log = [] 
                        for log in package_log_json["log"][test]:
                            if isinstance(log, list): 
                                build_log.extend([log_line for log_line in build_log])
                            else:
                                build_log.append(log)
                        package_log_json["log"][test] = {
                            "log": build_log,
                            "error": False, 
                            "stderr": []
                        }                   
                    
                    # Go to each log file and look through for each instantiate type and check if node_internal exists in the logs 
                    for line in package_log_json["log"][test]["log"]: 
                        
                        line_split = line.split("__,__")
                        try:
                            realwasm_log_type = line_split[1]
                            stack_trace = line_split[-1]
                        except Exception:                             
                            continue
                        
                        if realwasm_log_type in ["WebAssemblyInstantiateStreaming", "WebAssemblyInstantiate", "WebAssemblyInstance"]: 
                            num_wasm_inst += 1 
                            
                            stack_trace_line = re.search("\[\"Error(.*)\"\]", stack_trace).groups()[0]
                            stack_trace_funcs = []
                            for trace_line in stack_trace_line.split("\\n    at "): 
                                if len(trace_line) == 0: continue
                                match_groups = re.search("(.*) \((.*)\)", trace_line)
                                if match_groups == None: 
                                    func = None; loc = trace_line
                                else: 
                                    func, loc = match_groups.groups()[:2] 
                                stack_trace_funcs.append((func, loc))

                            print(f"{package_name} {test}")
                            for (func, loc) in stack_trace_funcs:
                                print(f"  {func}: {loc}")
                            print()

                            bool_node_internal = False
                            for (func, loc) in stack_trace_funcs: 
                                if not bool_node_internal and "node:internal" in loc:    
                                    bool_node_internal = True 
                                    num_node_internal_inst += 1
                                    node_internal_funcs.update([func])

                                #if "node:internal" in loc: 
                                #    print(loc)

                                #if "process.processImmediate" == func: 
                                #    print(stack_trace_line)
                                

    print(f"{num_wasm_inst} instantiation sites of WebAssembly in {len(no_static_wasm_repos)} repos.")
    print(f"{num_node_internal_inst} instantiation sites of WebAssembly via internal node calls in {len(no_static_wasm_repos)} repos.")
    for func, count in node_internal_funcs.most_common(): 
        print(f"  {func} called {count} times.")
    
    # lazyllhttp (node:internal/deps/undici/undici

def clone_repo(repo_full_name): 

    with open(REALWASM_JSON, 'r') as f: 
        realwasm = json.load(f)

    repo_json = realwasm[repo_full_name]
    
    full_name = repo_json["repo_metadata"]["full_name"]
    repo_fullname_path_safe = "__".join(full_name.split("/"))
    repo_dir = TESTING_REPO + "/" + repo_fullname_path_safe 

    # Clone repo
    clone_repo_at_sha(
        path_safe_repo_full_name=repo_fullname_path_safe,
        ssh=repo_json["repo_metadata"]["clone_url"],
        commit_sha=repo_json["repo_metadata"]["commit_SHA"], 
        dir=TESTING_REPO        
    )

    return repo_dir

def get_static_instantiation_type(): 

    with open(INSTANTIATION_JSON, 'r') as f: 
        package_to_client_to_instantiation_count = json.load(f)
    with open(REALWASM_JSON, 'r') as f: 
        realwasm = json.load(f)

    clients_and_packages_with_instantiate_call = {}
    for package, clients in package_to_client_to_instantiation_count.items(): 
        for client, inst_counts in clients.items(): 
            total_instantiation = sum(inst_counts.values()) 
            if total_instantiation == 0: 
                continue 
            total_client_instantiate_percent = 100*(
                (inst_counts["WebAssemblyInstantiate"] if "WebAssemblyInstantiate" in inst_counts else 0)  
                /total_instantiation)
            
            if total_client_instantiate_percent == 100: 
                if client not in clients_and_packages_with_instantiate_call: 
                    clients_and_packages_with_instantiate_call[client] = []
                if package not in clients_and_packages_with_instantiate_call[client]: 
                    clients_and_packages_with_instantiate_call[client].append(package)
    
    def get_grep_counts(dir): 
        # Grep for all three instantiation types in these packages.            

        grep_results = run(['grep', '-ro', 'WebAssembly.Instance('], cwd=dir, check=False)
        wasm_instance_count = 0 if grep_results.returncode != 0 else grep_results.stdout.count('\n')

        grep_results = run(['grep', '-ro', 'WebAssembly.instantiate('], cwd=dir, check=False)
        wasm_instantiate_count = 0 if grep_results.returncode != 0 else grep_results.stdout.count('\n')

        grep_results = run(['grep', '-ro', 'WebAssembly.instantiateStreaming('], cwd=dir, check=False)
        wasm_instantiateStreaming_count = 0 if grep_results.returncode != 0 else grep_results.stdout.count('\n')

        return {
            "Instance": wasm_instance_count, 
            "Instantiate": wasm_instantiate_count, 
            "InstantiateStreaming": wasm_instantiateStreaming_count
        }
    
    client_packages_static_insts = {}
    for client, package_list in clients_and_packages_with_instantiate_call.items(): 

        repo_dir = clone_repo(client)
        repo_json = realwasm[client]
        client_packages_static_insts[client] = {} 

        print(f"Analyzing {client}...")
        if 'self' in package_list: 
            client_packages_static_insts[client]['self'] = get_grep_counts(repo_dir)

        install_and_build_repo(repo_name=client, npm_filter_results=repo_json["npm_filter"], repo_dir=repo_dir)
        for package in package_list:
            if 'self' in package: continue
            client_packages_static_insts[client][package] = {}
            package_dir = f"{repo_dir}/node_modules/{package}"
            package_version = None
            if os.path.isfile(f"{package_dir}/package.json"): 
                with open(f"{package_dir}/package.json", 'r') as f: 
                    package_json = json.load(f)
                package_version = package_json["version"] if "version" in package_json else None 

            client_packages_static_insts[client][package] = get_grep_counts(f"{repo_dir}/node_modules/{package}")
            client_packages_static_insts[client][package]["version"] = package_version

        with open(PACKAGE_STATIC_INSTS, 'w+') as f:
            json.dump(client_packages_static_insts, f, ensure_ascii=False, indent=2)
        
        rm_rf_repo(repo_dir)

    with open(PACKAGE_STATIC_INSTS, 'w+') as f:
        json.dump(client_packages_static_insts, f, ensure_ascii=False, indent=2)

def instantiation_type_investigation(): 
    with open(INSTANTIATION_JSON, 'r') as f: 
        package_to_client_to_instantiation_count = json.load(f)
    with open(PACKAGE_STATIC_INSTS, 'r') as f:
        client_to_package_static_insts = json.load(f) 

    package_client_pairs = {}
    for package, clients in package_to_client_to_instantiation_count.items(): 
        for client, inst_counts in clients.items(): 
            total_instantiation = sum(inst_counts.values()) 
            if total_instantiation == 0: 
                continue 
            total_client_instantiate_percent = 100*(
                (inst_counts["WebAssemblyInstantiate"] if "WebAssemblyInstantiate" in inst_counts else 0)  
                /total_instantiation)
            
            if total_client_instantiate_percent == 100:
                if package not in package_client_pairs: 
                    package_client_pairs[package] = []
                if client not in package_client_pairs[package]: 
                    package_client_pairs[package].append(client)

    # Is it that in packages where WebAssembly.instantiate is always called, there are no static calls to other instantitation methods?
    # Out of 115 packages, 
    #  M only have calls to WebAssembly.instantiate() in the code 
    #  N have as many or more static calls to WebAssembly.instantiateStreaming()

    num_packages_only_calls_to_instantiate = 0 
    num_packages_calls_to_instantiateStreaming = 0 
    for package, clients in package_client_pairs.items(): 
        if package == "self": continue
        #print(f"For package {package}: ")

        bool_only_calls_to_instantiate = True
        bool_calls_to_instantiateStreaming = True 
        for client in clients: 
            static_info = client_to_package_static_insts[client][package]                        
            #print(f" {client}: {static_info}")
            bool_only_calls_to_instantiate = (static_info["Instantiate"] > 0 and static_info["Instance"] == 0 and static_info["InstantiateStreaming"] == 0) and bool_only_calls_to_instantiate
            bool_calls_to_instantiateStreaming = (static_info["InstantiateStreaming"] >= static_info["Instantiate"]) and bool_calls_to_instantiateStreaming
        
        num_packages_only_calls_to_instantiate += bool_only_calls_to_instantiate 
        num_packages_calls_to_instantiateStreaming += bool_calls_to_instantiateStreaming 

    print(f"{len(package_client_pairs)} packages only have calls to WebAssembly.Instantate()")
    print(f"{num_packages_only_calls_to_instantiate} packages only have calls to WebAssembly.instantiate()")
    print(f"{num_packages_calls_to_instantiateStreaming} packages have as many or more static calls to WebAssembly.instantiateStreaming()")

    # 115 packages only have calls to WebAssembly.Instantate()
    # 34 packages only have calls to WebAssembly.instantiate()
    # 54 packages have as many or more static calls to WebAssembly.instantiateStreaming()

# run(['mkdir', '-p', DEBUGGING_DIR])

#get_error_stats()
#no_static_wasm_investigation()
#get_static_instantiation_type()
#instantiation_type_investigation()
# no_static_wasm_check_dynamic_logs()

# https://github.com/emscripten-core/emscripten/issues/16913

# clone_repo("Karhdo/karhdo.dev")

'''
rm -rf node_modules && ./../../dynamic-analysis/untransform-dir.sh . && ./../../dynamic-analysis/transform-dir.sh . && npm i && npm run test  

[\"Error\\n
    at __realwasm_paper__log (/home/RealWasm/scripts/TESTING_REPO/hexojs__hexo-migrator-wordpress/test/index.js:8:20)\\n    
    at Proxy.<anonymous> (/home/RealWasm/scripts/TESTING_REPO/hexojs__hexo-migrator-wordpress/test/index.js:288:7)\\n
    at lazyllhttp (node:internal/deps/undici/undici:8532:32)\"]
'''

"""
[2024-06-25] 
There are five metrics along which we measure errors stats
- 102 repos do not have any statically reported WebAssembly
- 111 repos fail after instrumentation
-  37 repos have __realwasm in stderr output of test runs? Ignoring lint and logging errors.
-   8 repos have empty wasm hash dumps
-   9 repositories with mystery wasm hashes (aka, hashes that have been interoperated with but whose dump cannot be found).
-   0 unique wasm_hashes are mysteries.
"""
