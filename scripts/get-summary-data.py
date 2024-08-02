import json
import os
from collections import Counter

from utils import get_static_info, run
from utils import IGNORED_REPOS, SUMMARY_JSON_DIR, INSTANTIATION_JSON, WASM_STATIC_INFO_JSON, EXPORTS_CALLED_COUNT_JSON, CALLS_THROUGH_TABLE_JSON, WASM_IMPORTS_JSON, WASM_MODULES_INTEROP_TYPE, INTEROP_BUT_NEVER_INSTANTIATE

DYNAMIC_RESULTS = "./../data/dynamic-results"
DYNAMIC_RESULTS_JSON = "./../data/dynamic-results.json"
DUMPED_WASM_FILES = "./../data/dumped-wasm-files"

def get_file_and_static_info(repo_name_path_safe, wasm_hash, client_to_wasm_file_info): 
    
    wasm_hash_file = f"{DUMPED_WASM_FILES}/{repo_name_path_safe}/realwasm-module-{wasm_hash}.wasm"
    if os.path.isfile(wasm_hash_file): 
        # Get static info of the wasm file whose exports are being called
        if wasm_hash in client_to_wasm_file_info: 
            wasm_info = client_to_wasm_file_info[wasm_hash]
        else: 
            wasm_info = get_static_info(wasm_hash_file)
            client_to_wasm_file_info[wasm_hash] = wasm_info                                


def get_summary_data(): 

    package_to_client_to_instantiation_count = {}
    client_to_wasm_file_info = {}
    package_to_client_to_wasm_to_export_count = {}
    package_to_client_to_calls_through_table_count = {}
    wasm_hash_to_client_to_imports = {}
    interop_no_init = set()      
    wasm_modules_interop_type = {} # Out of all binaries that are instantiated, how many of them do not have any interoperation?
                                   # Record for each wasm binary, the clients (and tests) under which they are only instantiated vs interoperated with    

    dynamic_results = os.listdir(DYNAMIC_RESULTS)    

    for repo_results_dir in dynamic_results: 

        repo_first_name, repo_last_name = repo_results_dir.split("__")
        client_name = f"{repo_first_name}/{repo_last_name}"
        package_logs = os.listdir(f"{DYNAMIC_RESULTS}/{repo_results_dir}")

        if client_name in IGNORED_REPOS: continue

        for package_log in package_logs:
            package_name = "/".join(package_log.replace(".json", "").split("__"))
            package_log_file = f"{DYNAMIC_RESULTS}/{repo_results_dir}/{package_log}"
            with open(package_log_file, 'r') as f: 
                try: 
                    package_log_json = json.load(f)
                    print(f"Loaded {package_log_file}")
                except Exception as e:
                    print(f"Loading {package_log_file}: Exception raised {e}") 
                    return

            # Initialization for instantiation counts  
            if package_name not in package_to_client_to_instantiation_count: 
                package_to_client_to_instantiation_count[package_name] = {}
            if client_name not in package_to_client_to_instantiation_count[package_name]: 
                package_to_client_to_instantiation_count[package_name][client_name] = Counter()
                        
            # Initialization for export call counts 
            if package_name not in package_to_client_to_wasm_to_export_count: 
                package_to_client_to_wasm_to_export_count[package_name] = {}
            if client_name not in package_to_client_to_wasm_to_export_count[package_name]: 
                package_to_client_to_wasm_to_export_count[package_name][client_name] = {}

            # Initialization for calls through table 
            if package_name not in package_to_client_to_calls_through_table_count: 
                package_to_client_to_calls_through_table_count[package_name] = {}
            if client_name not in package_to_client_to_calls_through_table_count[package_name]: 
                package_to_client_to_calls_through_table_count[package_name][client_name] = {}

            repo_name_path_safe = client_name.replace("/", "__")
            for test in package_log_json["log"]:
                                
                for line in package_log_json["log"][test]["log"]: 

                    # NOTE: Each test is just added up. 
                    # Instead we should be able to disambiguate test logs so that we're not just logging multiple runs of the same test.
                    try: 
                        line_split = line.split("__,__")
                    except: 
                        print(f"In client {client_name}, package {package_name}, test {test}, could not split {line}")

                    try: 
                        realwasm_log_type = line_split[1]
                    except: 
                        print(f"Could not find realwasm_log_type for {line} for client {client_name}, package {package_name}, test {test}")                        
                        continue

                    # What percentage of WebAssembly binaries are instantiated via streaming, buffer and synchronously?
                    # "RealWasmLog,???,WebAssemblyInstance"
                    if realwasm_log_type in ["WebAssemblyInstantiateStreaming", "WebAssemblyInstantiate", "WebAssemblyInstance"]: 
                        package_to_client_to_instantiation_count[package_name][client_name].update([realwasm_log_type]) 

                    # What percentage of exported functions are called by JS?
                    # "RealWasmLog,???,WebAssemblyCallExport,6ad3d165078537d0630519e8b641374269ec0ef76722d75f57e572c53ab19247,Ia",
                    if realwasm_log_type == "WebAssemblyCallExport":
                        index = line_split.index("WebAssemblyCallExport")                        
                        try: 
                            wasm_hash, export_func_called = line_split[index+1], line_split[index+2] 
                            if "TODO" in wasm_hash or wasm_hash == "": 
                                continue
                        except Exception as e: 
                            print(f"Could not find wasmfile and export called for {line}")
                            continue                        
                        
                        # There is a CallExport so this wasm_hash has been interoperated with!
                        try: 
                            wasm_modules_interop_type[wasm_hash][client_name][package_name]["interop_type"].update(["CallExportedFunc"])
                        except Exception:
                            interop_no_init.add(wasm_hash)
                        
                        # Update counter for the times that this export is called
                        if wasm_hash not in package_to_client_to_wasm_to_export_count[package_name][client_name]: 
                            package_to_client_to_wasm_to_export_count[package_name][client_name][wasm_hash] = Counter()
                        package_to_client_to_wasm_to_export_count[package_name][client_name][wasm_hash].update([export_func_called])

                        get_file_and_static_info(repo_name_path_safe, wasm_hash, client_to_wasm_file_info)
                    
                    # Does JS ever invoke functions that are only exported through a table?
                    # Calls from JS to functions in imported table 
                    if realwasm_log_type == "WebAssemblyCallTableImport":
                        index = line_split.index("WebAssemblyCallTableImport")
                        wasm_hash, export_func_called = line_split[index+1], line_split[index+2] 
                        
                        if wasm_hash not in package_to_client_to_calls_through_table_count[package_name][client_name]: 
                            package_to_client_to_calls_through_table_count[package_name][client_name][wasm_hash] = {}
                            package_to_client_to_calls_through_table_count[package_name][client_name][wasm_hash]["counts"] = Counter() 
                            package_to_client_to_calls_through_table_count[package_name][client_name][wasm_hash]["functions_called"] = Counter()

                        package_to_client_to_calls_through_table_count[package_name][client_name][wasm_hash]["counts"].update(["WebAssemblyCallTableImport"]) 
                        package_to_client_to_calls_through_table_count[package_name][client_name][wasm_hash]["functions_called"].update([export_func_called])

                        get_file_and_static_info(repo_name_path_safe, wasm_hash, client_to_wasm_file_info)

                    if realwasm_log_type == "WebAssemblyCallTableExport":
                        index = line_split.index("WebAssemblyCallTableExport")
                        wasm_hash, export_func_called = line_split[index+1], line_split[index+2] 

                        # There is a CallTableExport so this wasm_hash has been interoperated with! 
                        try: 
                            wasm_modules_interop_type[wasm_hash][client_name][package_name]["interop_type"].update(["CallFuncInExportTable"])
                        except Exception:
                            interop_no_init.add(wasm_hash)
                        
                        if wasm_hash not in package_to_client_to_calls_through_table_count[package_name][client_name]: 
                            package_to_client_to_calls_through_table_count[package_name][client_name][wasm_hash] = {}
                            package_to_client_to_calls_through_table_count[package_name][client_name][wasm_hash]["counts"] = Counter() 
                            package_to_client_to_calls_through_table_count[package_name][client_name][wasm_hash]["functions_called"] = Counter()

                        package_to_client_to_calls_through_table_count[package_name][client_name][wasm_hash]["counts"].update(["WebAssemblyCallTableExport"]) 
                        package_to_client_to_calls_through_table_count[package_name][client_name][wasm_hash]["functions_called"].update([export_func_called])

                        get_file_and_static_info(repo_name_path_safe, wasm_hash, client_to_wasm_file_info)

                    # "RealWasmLog,???,WebAssemblyInstantiateWithHash,424d9e12e77cc4c9d38fc6c5ab46e95af543af3b898aa7e453acde9695fab5a2",
                    if realwasm_log_type == "WebAssemblyInstantiateWithHash": 
                        log_index = line_split.index("WebAssemblyInstantiateWithHash")
                        wasm_hash = line_split[log_index+1]
                        if "TODO" not in wasm_hash and wasm_hash != "":
                            # Record that this wasm hash has been instantiated 
                            if wasm_hash not in wasm_modules_interop_type:
                                wasm_modules_interop_type[wasm_hash] = {}
                            if client_name not in wasm_modules_interop_type[wasm_hash]: 
                                wasm_modules_interop_type[wasm_hash][client_name] = {}
                            if package_name not in wasm_modules_interop_type[wasm_hash][client_name]:
                                wasm_modules_interop_type[wasm_hash][client_name][package_name] = {
                                    "interop_type": Counter()
                                }
                            wasm_modules_interop_type[wasm_hash][client_name][package_name]["interop_type"].update(["Init"])
                            get_file_and_static_info(repo_name_path_safe, wasm_hash, client_to_wasm_file_info)
                    
                    # NOTE:
                    # "RealWasmLog,???,WebAssemblyImport,a682b6de06d21cab94a0b207216c48a10eff7c303e9ccf8e3912ab223aae3fe0,global,NaN,Number,null",
                    # "RealWasmLog,???,WebAssemblyImport,a682b6de06d21cab94a0b207216c48a10eff7c303e9ccf8e3912ab223aae3fe0,global,Infinity,Number,null",
                    # "RealWasmLog,???,WebAssemblyImport,a682b6de06d21cab94a0b207216c48a10eff7c303e9ccf8e3912ab223aae3fe0,env,_emscripten_memcpy_big,Function",
                    #   if (import_type_name === "Number") {
                    #     __realwasm_paper__log("WebAssemblyImport",hash,groupName,importName,import_type_name,import_);
                    #   } else {
                    #     __realwasm_paper__log("WebAssemblyImport",hash,groupName,importName,import_type_name);
                    #   } 
                    if realwasm_log_type == "WebAssemblyImport": 
                        log_index = line_split.index("WebAssemblyImport")
                        wasm_hash = line_split[log_index+1]
                        if "TODO" not in wasm_hash and wasm_hash != "": 
                            if wasm_hash not in wasm_hash_to_client_to_imports: 
                                wasm_hash_to_client_to_imports[wasm_hash] = {}
                            if client_name not in wasm_hash_to_client_to_imports[wasm_hash]:
                                wasm_hash_to_client_to_imports[wasm_hash][client_name] = {}
                            # if Number: hash,groupName,importName,import_type_name, import_
                            # else: no import_ 
                            groupName, importName, import_type_name = line_split[log_index+2:log_index+5]
                            if import_type_name == "Number": 
                                import_value = line_split[log_index+5]
                                import_obj = (import_type_name, import_value)
                            else: 
                                import_obj = (import_type_name)
                            if groupName not in wasm_hash_to_client_to_imports[wasm_hash][client_name]: 
                                wasm_hash_to_client_to_imports[wasm_hash][client_name][groupName] = {}
                            wasm_hash_to_client_to_imports[wasm_hash][client_name][groupName][importName] = import_obj   

    with open(INSTANTIATION_JSON, 'w+') as f: 
        json.dump(package_to_client_to_instantiation_count, f, ensure_ascii=False, indent=2)
    print(f"Dumping Instantiation Counter for dataset in {INSTANTIATION_JSON}")
    
    with open(WASM_STATIC_INFO_JSON, 'w+') as f: 
        json.dump(client_to_wasm_file_info, f, ensure_ascii=False, indent=2)
    print(f"Static info for wasm binaries in {WASM_STATIC_INFO_JSON}")
    
    with open(EXPORTS_CALLED_COUNT_JSON, 'w+') as f: 
        json.dump(package_to_client_to_wasm_to_export_count, f, ensure_ascii=False, indent=2)
    print(f"Exported called counter in {EXPORTS_CALLED_COUNT_JSON}")
    
    with open(CALLS_THROUGH_TABLE_JSON, 'w+') as f: 
        json.dump(package_to_client_to_calls_through_table_count, f, ensure_ascii=False, indent=2)
    print(f"Calls through table counter in {CALLS_THROUGH_TABLE_JSON}")
    
    with open(WASM_IMPORTS_JSON, 'w+') as f: 
        json.dump(wasm_hash_to_client_to_imports, f, ensure_ascii=False, indent=2)
    print(f"Wasm Imports in {WASM_IMPORTS_JSON}")
    
    with open(WASM_MODULES_INTEROP_TYPE, 'w+') as f: 
        json.dump(wasm_modules_interop_type, f, ensure_ascii=False, indent=2)
    print(f"A Counter on the Type of Interop (Init, CallExportedFunc, CallFuncInExportTable) over Wasm Hashes in the dataset {WASM_MODULES_INTEROP_TYPE}")
    
    with open(INTEROP_BUT_NEVER_INSTANTIATE, 'w+') as f: 
        json.dump(list(interop_no_init), f, ensure_ascii=False, indent=2)
    print(f"Wasm Hashes that show interop but no init are in {INTEROP_BUT_NEVER_INSTANTIATE}")

run(['mkdir', '-p', SUMMARY_JSON_DIR])
get_summary_data()