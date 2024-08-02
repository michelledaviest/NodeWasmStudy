import json

from collections import Counter
import os

from utils import clone_repo_at_sha, install_and_build_repo, rm_rf_repo, run, hash_wasm_file
from utils import TESTING_REPO, REALWASM_JSON, DEP_ANLYSIS_JSON, ANALYZED_REPOS_JSON

GET_WASM_SOURCE_ANALYSIS = "./get-wasm-source/get-wasm-source.js"

def get_wasm_hashes(repo_dir): 
    wasm_files = set()    
    wasm_sources_with_hash = {
        "array": [], 
        "base64": [], 
        "binary": [], 
    }

    for root, _dirs, files in os.walk(repo_dir):
        for file in files:            
            path_to_file = os.path.join(root, file)

            if not os.path.isfile(path_to_file):
                continue  

            if file.endswith(".wasm"):
                wasm_files.add(path_to_file)
                binary_hash = hash_wasm_file(path_to_file)
                wasm_sources_with_hash["binary"].append(binary_hash)

            elif (file.endswith(".js") or file.endswith(".ts") or file.endswith(".cjs") or file.endswith(".mjs")): 
                  # Sometimes wasm modules reside in files with no extension. Ex: in k0warite/rxt
                try: 
                    result = run(['node', GET_WASM_SOURCE_ANALYSIS, path_to_file], check=False)
                    if result.returncode == 0: 
                        wasm_hashes_dict = json.loads(result.stdout)
                        if True in [len(wasm_hashes)>0 for source, wasm_hashes in wasm_hashes_dict.items()]:                        
                            wasm_files.add(path_to_file)
                            wasm_sources_with_hash["array"].extend(wasm_hashes_dict["array"])
                            wasm_sources_with_hash["base64"].extend(wasm_hashes_dict["base64string"])

                except TimeoutError: 
                    continue

    return (list(wasm_files), wasm_sources_with_hash)

def de_duplicate(wasm_sources_with_hash):

    binary_hashes = set(wasm_sources_with_hash["binary"])
    array_hashes = set(wasm_sources_with_hash["array"])
    base64_hashes = set(wasm_sources_with_hash["base64"])

    # Get counts for unique wasm hashes in each wasm source 
    unique_wasm_counts = {
        "array": 0, 
        "base64": 0, 
        "binary": 0, 
    }
    unique_wasm_counts["array"]  = len(array_hashes.difference(binary_hashes).difference(base64_hashes))#.difference(wasmjs_hashes))
    unique_wasm_counts["base64"] = len(base64_hashes.difference(binary_hashes).difference(array_hashes))#.difference(wasmjs_hashes))
    unique_wasm_counts["binary"] = len(binary_hashes.difference(array_hashes).difference(base64_hashes))#.difference(wasmjs_hashes))

    # Get de-duplication stats, ie, how often are wasm hashes duplicated across different sources and the same group 
    de_duplication_stats = {
        "array": 0, "base64": 0, "binary": 0, 
        "array_&_base64": 0, "array_&_binary": 0, "base64_&_binary": 0,
        "array_&_base64_&_binary": 0,
    }

    de_duplication_stats["array"] = len(wasm_sources_with_hash["array"]) - len(array_hashes)
    de_duplication_stats["base64"] = len(wasm_sources_with_hash["base64"]) - len(base64_hashes)
    de_duplication_stats["binary"] = len(wasm_sources_with_hash["binary"]) - len(binary_hashes)

    de_duplication_stats["array_&_base64"]          = len(array_hashes.intersection(base64_hashes))
    de_duplication_stats["array_&_binary"]          = len(array_hashes.intersection(binary_hashes))
    de_duplication_stats["base64_&_binary"]         = len(base64_hashes.intersection(binary_hashes))

    de_duplication_stats["array_&_base64_&_binary"] = len(array_hashes.intersection(base64_hashes).intersection(binary_hashes))

    return (unique_wasm_counts, de_duplication_stats)

def get_wasm_files_for_repo(repo_json): 

    full_name = repo_json["repo_metadata"]["full_name"]
    repo_fullname_path_safe = "__".join(full_name.split("/"))
    repo_dir = TESTING_REPO + "/" + repo_fullname_path_safe 

    #print(f"Analyzing {full_name}")

    # Clone repo
    #print("Cloning...")
    clone_repo_at_sha(
        path_safe_repo_full_name=repo_fullname_path_safe,
        ssh=repo_json["repo_metadata"]["clone_url"],
        commit_sha=repo_json["repo_metadata"]["commit_SHA"], 
        dir=TESTING_REPO        
    )
    
    # Install and Build 
    #print("Installing and Building...")
    install_and_build_repo(repo_name=repo_json["repo_metadata"]["name"], repo_dir=repo_dir, npm_filter_results=repo_json["npm_filter"])    

    # Find wasm files in repo 
    #print("Finding Wasm Hashes...")
    (wasm_files, wasm_sources_with_hash) = get_wasm_hashes(repo_dir) 
    (unique_wasm_counts, de_duplication_stats) = de_duplicate(wasm_sources_with_hash)

    rm_rf_repo(repo_dir)

    return (full_name, {        
        "files_with_wasm": wasm_files,
        "wasm_sources_with_hash": wasm_sources_with_hash,
        "unique_wasm_counts": unique_wasm_counts,
        "de_duplication_stats": de_duplication_stats 
    }) 

def get_wasm_files_in_dataset():

    with open(DEP_ANLYSIS_JSON, 'r') as f: 
        dep_analysis_results = json.load(f)

    with open(REALWASM_JSON, 'r') as f: 
        realwasm = json.load(f)

    worklist = [realwasm[repo] for repo in realwasm if realwasm[repo]["repo_metadata"]["full_name"] not in dep_analysis_results]    
    if len(worklist) == 0: 
        print("Done analyzing packages for WebAssembly Modules.") 
        return 
    
    print(f"Analysing {len(worklist)} packages for WebAssembly modules.")
    
    # Multiprocessing 
    #with Pool() as pool:
    #    for result in pool.imap(get_wasm_files_for_repo, worklist, chunksize=1):
    #        (full_name, json_result) = result
    #        dep_analysis_results[full_name] = json_result 
    #        print(f"{full_name}: {json_result['wasm_sources']}")
    #        with open(DEP_ANLYSIS_JSON, 'w') as f:
    #            json.dump(dep_analysis_results, f, ensure_ascii=False, indent=2)

    # Serial version 
    for count, repo_full_name in enumerate(worklist):

        (full_name, result) = get_wasm_files_for_repo(repo_json=realwasm[repo_full_name])
        dep_analysis_results[full_name] = result 
        print(f"({count}/{len(worklist)}): {full_name} {result['unique_wasm_counts']}")

        with open(DEP_ANLYSIS_JSON, 'w') as f:
            json.dump(dep_analysis_results, f, ensure_ascii=False, indent=2)

def flatten_tree(graph):
    if isinstance(graph, list): 
        return graph
    else: 
        nodes = []
        for lib in graph: 
            nodes += [lib] + flatten_tree(graph[lib]) 
        return list(set(nodes)) 

def get_dependency_tree(wasm_files):

    # In NodeJS packages can exist in node_modules and in packages defined in workspaces (which can have their own node_modules)
    # Workspaces: https://docs.npmjs.com/cli/v7/using-npm/workspaces
    # The expected result once running npm install, is that the workspace folder will get symlinked to the node_modules folder of the current working dir.
    # But the path of the file with wasm will still show up under the workspace folder. 

    # However, these packages in a workspace are not distributed under NPM and are shipped with the repo/package itself.
    # We only get a dependency tree for packages distributed via NPM  


    dependency_tree = {}            # full dependency tree. Each entry is a package and it records the packages it depends
                                    # The dependency tree is only for packages that have WebAssembly modules in it. 
    package_to_wasm_module = {}     # mapping from each package used in this repo to the files in it that contain wasm 
    wasm_files_in_repo = []         # files in the repo itself (that have WebAssembly modules in it)  

    for wasm_file_path in wasm_files:
        path_to_record = "./"+"/".join(wasm_file_path.split("/")[3:])
        parent_package  = None
        
        ## If workspace exists in the current path, add the package name to the parent_package name 
        #for workspace in workspaces: 
        #
        #    # If no *, the workspace is the current package
        #    if "*" not in workspace:
        #        if workspace in wasm_file_path: 
        #            parent_package = workspace.split("/")[-1]
        #            dependency_tree[parent_package] = []
        #
        #    # If the workspace has a * at the end of the path, everything after that is a package 
        #    else: 
        #        workspace_without_star = workspace.replace("*", "")
        #        if workspace_without_star in wasm_file_path: 
        #            parent_package = wasm_file_path.split(workspace_without_star)[1].split("/")[0]
        #            dependency_tree[parent_package] = []
        #
        #print(wasm_file_path)
        #print(parent_package)

        # Remove everything upto the first 'node_modules'
        wasm_file_path_mod = "node_modules".join(wasm_file_path.split("node_modules")[1:]) 
        wasm_file_recorded = False
        for path in wasm_file_path_mod.split("node_modules"):

            # Split on "/" to get each component in the path 
            path_split = [t for t in path.split("/") if t != '' and t != '.']          
            if len(path_split) == 0: 
                continue

            # Get the current package name 
            current_package = path_split[0]
            if current_package[0] == "@": 
                current_package = "/".join(path_split[:2])                        
            if current_package[0] == ".": 
                # If the current package is under .bin or something, it isn't a package 
                # Its a folder where binaries (executables) from your node modules are located.
                # Skip and save under parent package  
                continue

            # We track the dependency tree by tracking the current parent package
            # If the current parent package is None, update the parent package and add an entry in the dependency tree 
            if parent_package is None: 
                if current_package not in dependency_tree: 
                    dependency_tree[current_package] = []
                parent_package  = current_package

            # If the current parent package is not None, add current package to the dependecy tree under the parent package
            else: 
                if parent_package not in dependency_tree: 
                    dependency_tree[parent_package] = [current_package]  
                else:
                    if current_package not in dependency_tree[parent_package]:   
                        dependency_tree[parent_package] = dependency_tree[parent_package] + [current_package]                                     
                parent_package = current_package
            
            # If the path has a file in it, we have reached the end of this package dependencies to this file 
            if path.split("/")[-1] != '': 
                wasm_file_recorded = True
                # Add to map from package_to_wasm_module under the current package 
                if current_package not in package_to_wasm_module: 
                    package_to_wasm_module[current_package] = []
                if path_to_record not in package_to_wasm_module[current_package]: 
                    package_to_wasm_module[current_package].append(path_to_record)
    
        # If the wasm file has not been recorded, it either belongs to the repo or a package in a workspace that did not have any node_modules in it 
        if not wasm_file_recorded: 

            if parent_package is None: 
                wasm_files_in_repo.append(path_to_record)

            else:
                if parent_package not in package_to_wasm_module: 
                    package_to_wasm_module[parent_package] = []
                if path_to_record not in package_to_wasm_module[parent_package]: 
                    package_to_wasm_module[parent_package].append(path_to_record)
    
    return (dependency_tree, package_to_wasm_module, wasm_files_in_repo)

def dependency_analysis_for_dataset(): 

    with open(DEP_ANLYSIS_JSON, 'r') as f: 
        dep_analysis_results = json.load(f)

    for repo in dep_analysis_results:

        full_name = repo
        wasm_files = dep_analysis_results[repo]["files_with_wasm"]
        (dependency_tree, package_to_wasm_module, wasm_files_in_repo) = get_dependency_tree(wasm_files)    

        client_for = flatten_tree(dependency_tree)
        assert(len(set([val for value in package_to_wasm_module.values() for val in value ])) + len(set(wasm_files_in_repo)) == len(set(wasm_files)))

        dep_analysis_results[full_name]["client_for"] = client_for
        dep_analysis_results[full_name]["first_order_package_dependencies"] = [dep for dep in dependency_tree]
        dep_analysis_results[full_name]["package_dependency_tree"] = dependency_tree
        dep_analysis_results[full_name]["package_to_wasm_module"] = package_to_wasm_module
        dep_analysis_results[full_name]["wasm_modules_in_repo"] = wasm_files_in_repo            

        with open(DEP_ANLYSIS_JSON, 'w') as f:
            json.dump(dep_analysis_results, f, ensure_ascii=False, indent=2)

# Make sure each repo for which we have results are in the repo. 
def make_sure_results_are_consistent(): 

    with open(DEP_ANLYSIS_JSON, 'r') as f: 
        dep_analysis_results = json.load(f)
    
    with open(REALWASM_JSON, 'r') as realwasm_f: 
        realwasm = json.load(realwasm_f)

    worklist = list(dep_analysis_results.keys())
    for repo_name in worklist: 
        if repo_name not in realwasm: 
            print(f"{repo_name} not in dataset anymore. Removing.")
            del dep_analysis_results[repo_name]
    
    with open(DEP_ANLYSIS_JSON, 'w') as f:
            json.dump(dep_analysis_results, f, ensure_ascii=False, indent=2)

run(["mkdir", "-p", TESTING_REPO])
make_sure_results_are_consistent()

get_wasm_files_in_dataset() 
dependency_analysis_for_dataset()
