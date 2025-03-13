import json
import shlex 
import numpy as np
import statistics
from collections import Counter
import argparse
import pathlib
import pandas as pd 
import os 
import re
import datetime

from utils import REALWASM_JSON, DEP_ANLYSIS_JSON, DUMPED_WASM_FILES, IGNORED_REPOS
from utils import NUM_TOP_PACKAGES_TO_ANALYZE, ANALYZED_REPOS_JSON, ANALYZED_NPM_PACKAGES_JSON
from utils import plt, run
from utils import INSTANTIATION_JSON, WASM_STATIC_INFO_JSON, EXPORTS_CALLED_COUNT_JSON, CALLS_THROUGH_TABLE_JSON, WASM_IMPORTS_JSON, WASM_MODULES_INTEROP_TYPE, INTEROP_BUT_NEVER_INSTANTIATE, SUMMARY_JSON_DIR

GRAPH_DIR = "./../data/graphs"
WASM_SOURCE_GRAPH = f'{GRAPH_DIR}/wasm-source-graph.pdf' 

FREQ_DIST_DYNAMIC_CLIENTS_PACKAGES = f'{GRAPH_DIR}/packages-freq-dynamic-clients.pdf'
FREQ_DIST_STATIC_CLIENTS_WASM_HASH = f'{GRAPH_DIR}/wasm-hash-freq-static-clients.pdf'
FREQ_DIST_DYNAMIC_CLIENTS_WASM_HASH = f'{GRAPH_DIR}/wasm-hash-freq-dynamic-clients.pdf'

INSTANTIATION_GRAPH_FILE = f'{GRAPH_DIR}/instantiation.pdf'
CALLS_THROUGH_TAB_VS_FUNC = f'{GRAPH_DIR}/calls-through-tab-vs-funcs.pdf'
PERCENT_EXPORTED_FUNCS_CALLED = f'{GRAPH_DIR}/percent-exported-funcs-called.pdf'
SCATTER_PLOT_PERCENT_EXPORTED_FUNCS_CALLED = f'{GRAPH_DIR}/scatter-plot-percent-exported-funcs-called.pdf'
PERCENT_FUNCS_IN_EXPORTED_TABLE_CALLED = f'{GRAPH_DIR}/percent-funcs-in-exported-table-called.pdf'
TABLE_MODIFIED_PERCENT = f'{GRAPH_DIR}/table-modified.pdf'
EXPORTS_NEVER_CALLED = f'{GRAPH_DIR}/exports-never-called.pdf'

DEBLOAT_BINS_DIR = "./../data/debloat-binaries"
METADCE_BIN = "./wasm-metadce"
DCE_STATS = f"{SUMMARY_JSON_DIR}/dce-stats.json"
DCE_GRAPH = f'{GRAPH_DIR}/dce.pdf'

WASM_EVOLUTION_JSON = "./../data/wasm-evolution.json"
WASM_EVOLUTION_GRAPH = f"{GRAPH_DIR}/wasm_evolution_security.pdf"

def general_dataset_stats():
    
    with open(REALWASM_JSON, 'r') as f: 
        realwasm = json.load(f) 

    with open(ANALYZED_NPM_PACKAGES_JSON, 'r') as f:
        scraped_npm_packages = json.load(f) 

    with open(ANALYZED_REPOS_JSON, 'r') as f: 
        analyzed_repos = json.load(f)

    error_counter = Counter() 

    for repo in analyzed_repos:
        # "FAILURE": "Not JS project or Install/Build failed or No running tests"
        if "FAILURE" in analyzed_repos[repo]:
            fail_reason = analyzed_repos[repo]["FAILURE"]
            fail_reason = "Install/Build fail" if "Install/Build fail" in fail_reason else fail_reason
            fail_reason = "Exception" if "Exception" in fail_reason else fail_reason
            error_counter.update([fail_reason]) 

            if repo in realwasm: 
                print(f"{repo} is reported to have a FAILURE and is in the dataset.")

        elif repo not in realwasm: 
            print(f"{repo} does not have a FAILURE but is not in the dataset") 

    for repo in realwasm: 
        if repo not in analyzed_repos: 
            print(f"Repo {repo} in dataset and not in analyzed repos.") 
    
    repos_we_have_data_for = sum(error_counter.values()) + len(realwasm)
    assert repos_we_have_data_for == len(analyzed_repos), f"Repos we have data for ({repos_we_have_data_for}) do not match up with number of analyzed repos ({len(analyzed_repos)})."

    def pretty_print_number(n): 
        num_spaces = 4-len(str(n))
        return f"{num_spaces*' '}{n}"

    num_npm_packages_scraped = len(scraped_npm_packages) - NUM_TOP_PACKAGES_TO_ANALYZE
    print("RealWasm Dataset Stats:")
    print(f"We scraped {num_npm_packages_scraped} packages from NPM that contain keyword 'wasm'/'WebAssembly'.")
    print(f"We also analyzed {NUM_TOP_PACKAGES_TO_ANALYZE} packages of the top most downloaded packages from NPM.")
    print(f"We analyzed {len(analyzed_repos)} number of possible clients of these NPM packages.")
    print("Of these,")
    error_counter = error_counter.most_common()
    for (error_msg, count) in error_counter:
        print(f" {pretty_print_number(count)} had failure reason: {error_msg}")
    print(f"Total {len(realwasm)} repos found for dataset.")


def answer_package_dependency_research_questions():

    with open(DEP_ANLYSIS_JSON, 'r') as f: 
        dep_analysis_results = json.load(f)

    with open(REALWASM_JSON, 'r') as f: 
        realwasm = json.load(f)

    missing_packages = [pack for pack in realwasm if pack not in dep_analysis_results.keys()]
    assert len(missing_packages) == 0, f"Missing package dependency results: {missing_packages}"

    # Research questions: 
    # How many packages depend on WebAssembly only directly?  
    # How many packages depend on WebAssembly only indirectly? 
    # How many packages depend on WebAssembly indirectly and directly? 
    # How many packages indirectly depend on more than one NPM package with a WebAssembly binary?
    # How many packages ship with more than one WebAssembly binary? 
    # How many packages depend on other NPM packages with WebAssembly binaries? 
    # Which packages in the dataset are depended on the most? 

    package_dep_graph = {}                # Map each repo to the dependency graph 
    package_to_wasm_module = {}  # Map each (wasm) package in dataset to wasm modules it contains 
    package_first_order_ind_deps = {}     # Map each repo to its first order dependencies, ie, children of root 
    indirect_dependencies = {}            # Map each repo to its indirect dependencies 
    
    packages_dep_only_direct = set()
    packages_dep_only_indirect = set()
    packages_dep_direct_and_indirect = set()
    packages_no_static_wasm = set()

    for pack, analysis_results in dep_analysis_results.items(): 

        package_dep_graph[pack] = analysis_results["package_dependency_tree"]
        package_first_order_ind_deps[pack] = analysis_results["first_order_package_dependencies"]
        indirect_dependencies[pack] = analysis_results["client_for"]

        package_to_wasm_module[pack] = analysis_results["files_with_wasm"] 
        # Get modules associated with indirect packages
        # for ind_package, modules in package_to_wasm_module.items(): 
        #     if ind_package in package_to_wasm_module: 
        #         package_to_wasm_module[ind_package].extend(modules)
        #     else: 
        #         package_to_wasm_module[ind_package] = modules 

        # Check if it has a direct or indirect dependency on Wasm or no static Wasm
        num_indirect_dependencies = len(analysis_results["client_for"])
        num_direct_dependencies = len(analysis_results["wasm_modules_in_repo"])
        if num_direct_dependencies == 0 and num_indirect_dependencies == 0: 
            packages_no_static_wasm.add(pack)
            continue
        if num_direct_dependencies == 0: packages_dep_only_indirect.add(pack)
        if num_indirect_dependencies == 0: packages_dep_only_direct.add(pack)
        if num_indirect_dependencies > 0 and num_direct_dependencies > 0: 
            packages_dep_direct_and_indirect.add(pack)
        

    total_packages = len(dep_analysis_results)
    missing_dep_data_for_packs = total_packages - (len(packages_no_static_wasm) + len(packages_dep_only_direct) + len(packages_dep_only_indirect) + len(packages_dep_direct_and_indirect))
    assert missing_packages != 0, f"Dependency data for {missing_dep_data_for_packs} packages is missing."

    repos_more_than_one_package = set()
    package_dep_other_packages = set()
    top_packages = Counter()

    for pack in package_dep_graph: 
        dep_graph = package_dep_graph[pack]

        # Check if it depends on more than one NPM package 
        if len(dep_graph.keys()) > 1: 
            repos_more_than_one_package.add(pack)

        # Get flat list of all packages that this repo depends on  
        top_packages.update(indirect_dependencies[pack])

        # Check if the packages depend on other packages 
        for package in dep_graph: 
            if len(dep_graph[package]) > 0: 
                package_dep_other_packages.add(package)
            #else: 
                # The dependencies of a package can be different in different repos, 
                # because you have different versions of packages floating around
                # Example: NPM package assemblyscript
                # In repo semaphore-protocol/semaphore, the assemblyscript package depends on the package long which has WebAssembly in it 
                # In repo p455555555/WebAssembly-TOTP, it does not have any packages it depends on 
                #if package in package_dep_other_packages:
        
    packages_with_more_than_one_wasm_file = set()    
    for package in package_to_wasm_module:
        if len(package_to_wasm_module[package]) > 1: 
            packages_with_more_than_one_wasm_file.add(package)
    #total_number_of_indirect_packages = len(indirect_package_to_wasm_module)
    
    print()
    print("RealWasm Dependency analysis:")
    print(f"Total number of packages in dataset: {total_packages}")
    print(f"How many packages do not have any static wasm?: {len(packages_no_static_wasm)}")
    print(f"How many packages depend on WebAssembly only directly? {len(packages_dep_only_direct)}")
    print(f"How many packages depend on WebAssembly only indirectly? {len(packages_dep_only_indirect)}")
    print(f"How many packages depend on WebAssembly indirectly and directly? {len(packages_dep_direct_and_indirect)}")
    print(f"How many packages indirectly depend on more than one NPM package with a WebAssembly binary? {len(repos_more_than_one_package)}/{total_packages} ({100*(len(repos_more_than_one_package)/total_packages):.2f})%")
    print(f"How many packages ship with more than one WebAssembly binary? {len(packages_with_more_than_one_wasm_file)}/{total_packages} ({100*(len(packages_with_more_than_one_wasm_file)/total_packages):.2f})%")
    print(f"How many packages depend on other NPM packages with WebAssembly binaries? {len(package_dep_other_packages)}/{total_packages} ({100*(len(package_dep_other_packages)/total_packages):.2f})%")
    print("Which NPM packages in the dataset are depended on the most? ")
    for package in top_packages.most_common()[:10]: 
        package, package_count = package
        print(f"  {package} depended upon by {package_count} packages")

def wasm_source_graph(): 

    with open(DEP_ANLYSIS_JSON, 'r') as f: 
        dep_analysis_results = json.load(f)

    WASM_SOURCES = ["binary", "base64", "array"]

    ignored_repos = []  # Ignored since they have more than 100 Wasm modules
    no_static_wasm_repos = []
    realwasm_wasm_sources = {}
    total_repos = 0
    repos_with_weird_no_wasm = []
    repos_with_greater_than_45_wasms = []
    for repo, analysis_results in dep_analysis_results.items(): 
        total_repos += 1
        total_wasm_modules_in_repo = sum(analysis_results["unique_wasm_counts"].values())
        if total_wasm_modules_in_repo >= 45 and total_wasm_modules_in_repo < 80: 
            print(f'{repo} : {total_wasm_modules_in_repo} Wasm modules')
            repos_with_greater_than_45_wasms.append(repo)
        # ind_plus_dir_deps = len(analysis_results["client_for"]) + len(analysis_results["wasm_modules_in_repo"])
        # if (total_wasm_modules_in_repo == 0 and ind_plus_dir_deps != 0) or (total_wasm_modules_in_repo != 0 and ind_plus_dir_deps == 0): 
        #     repos_with_weird_no_wasm.append(repo)            

        if total_wasm_modules_in_repo > 80: 
            ignored_repos.append(repo)
            continue       
        if total_wasm_modules_in_repo == 0: 
            no_static_wasm_repos.append(repo)
            continue
        realwasm_wasm_sources[repo] = Counter({wasm_source: 0 for wasm_source in WASM_SOURCES})
        realwasm_wasm_sources[repo].update(analysis_results['unique_wasm_counts'])

    total_num_wasm_modules = sum([x for repo in realwasm_wasm_sources for x in realwasm_wasm_sources[repo].values()])
    total_repos_in_graph = len(realwasm_wasm_sources.keys())
    
    # Total Number of Wasm modules 
    # Number of Repos and Number of Wasm modules for each wasm source type
    # Wasm Modules for which there is no statically reported WebAssembly Module 
    # Most popular wasm source by wasm module
    # Most popular wasm source by repo 

    print(f"Wasm Module Source Data for {total_repos} repositories in RealWasm dataset.")
    print(f"{len(ignored_repos)} outliers removed. Following repositories are outliers: {ignored_repos}")
    print(f"{len(no_static_wasm_repos)} repos have no statically reported WebAssembly. Repositories are removed.")
    print(f"{repos_with_greater_than_45_wasms} repos contain more than 45 Wasm modules.")
    print(f"{total_num_wasm_modules} total number of WebAssembly Modules in dataset.")    

    source_to_repo_and_module_count = {}
    for source in WASM_SOURCES:
        repos_with_source = [repo for repo in realwasm_wasm_sources if realwasm_wasm_sources[repo][source] != 0]
        count_modules_with_source = sum([realwasm_wasm_sources[repo][source] for repo in realwasm_wasm_sources])
        source_to_repo_and_module_count[source] = {
            'repositories': repos_with_source, 
            'modules_count': count_modules_with_source
        }
        print(f"{len(repos_with_source)}/{total_repos_in_graph} repositories and {count_modules_with_source}/{total_num_wasm_modules} wasm modules have WebAssembly source {source}")
 
    wasm_source_popularity_by_repo = [k for k, v in sorted(source_to_repo_and_module_count.items(), key=lambda item: len(item[1]['repositories']), reverse=True)]
    print(f"Wasm module source popularity by repository: {wasm_source_popularity_by_repo}")

    wasm_source_popularity_by_module = [k for k, v in sorted(source_to_repo_and_module_count.items(), key=lambda item: item[1]['modules_count'], reverse=True)]
    print(f"Wasm module source popularity by module: {wasm_source_popularity_by_module}")

    # Stacked Bar chart of the different sources of WebAssembly in the different repos 

    # Create sorted data: a list for every wasm source, sorted by repos with least wasm modules to most
    sorted_repo_names = [k for k, _v in sorted(realwasm_wasm_sources.items(), key=lambda item: sum(item[1].values()), reverse=True)]
    wasm_source_data = {source: [] for source in wasm_source_popularity_by_module} 
    for repo in sorted_repo_names:
        wasm_sources_for_repo = realwasm_wasm_sources[repo]
        for source in wasm_source_data:             
            wasm_source_data[source].append(wasm_sources_for_repo[source] if source in wasm_sources_for_repo else 0)         
    repo_names = np.arange(0, len(sorted_repo_names))
    wasm_source_data = {source: np.array(values) for source, values in wasm_source_data.items()}  

    plt.figure(figsize=(17, 10))

    # plot bars in stack manner
    bar_width = 0.9
    colors = ['tab:red', 'tab:blue', 'tab:green', 'tab:olive']
    bottom = []
    for count, source in enumerate(wasm_source_data):
        if count == 0: 
            plt.bar(repo_names, wasm_source_data[source], color=colors[count], width=bar_width, edgecolor = "none")
            bottom = wasm_source_data[source]
        else: 
            plt.bar(repo_names, wasm_source_data[source], bottom=bottom, color=colors[count], width=bar_width, edgecolor = "none")
            bottom += wasm_source_data[source]
    
    plt.xlabel("Packages (sorted by number of modules)")
    plt.ylabel("\# Unique WebAssembly modules")

    plt.legend([key.capitalize() for key in wasm_source_data.keys()])
    plt.savefig(WASM_SOURCE_GRAPH, bbox_inches='tight')
    plt.clf()

    print(f"Wasm Source Graph at {WASM_SOURCE_GRAPH}")

def de_duplication_stats(): 
    
    with open(DEP_ANLYSIS_JSON, 'r') as f: 
        dep_analysis_results = json.load(f)

    package_percent_duplicated = []
    for package, results in dep_analysis_results.items(): 
        wasm_hashes = [wasm_hash 
            for wasm_hashes in results["wasm_sources_with_hash"].values()
            for wasm_hash in wasm_hashes             
        ]
        count_total = len(wasm_hashes)
        count_unique = len(set(wasm_hashes))
        duplicated_wasm_hashes = count_total - count_unique
        package_percent_duplicated.append(
            100*(duplicated_wasm_hashes/count_total)
            if count_total > 0 else 0 
        )
    import statistics
    print(f"A mean of {statistics.mean(package_percent_duplicated):.2f}% and a median of {statistics.median(package_percent_duplicated):.2f}% Wasm modules are duplicated within a package ")

    # total_de_duplication_stats = {
    #     "array": 0, "base64": 0, "binary": 0, 
    #     "array_&_base64": 0, "array_&_binary": 0, "base64_&_binary": 0,
    #     "array_&_base64_&_binary": 0,
    # }
    # wasm_hashes_counter = Counter() 
    # repo_count = 0 
    # for repo_full_name, repo_analysis_results in dep_analysis_results.items():
    #     if "wasm_sources_with_hash" in repo_analysis_results: 
    #         for key, value in repo_analysis_results["wasm_sources_with_hash"].items(): 
    #             wasm_hashes_counter.update(value)
    #     if "de_duplication_stats" in repo_analysis_results: 
    #         repo_count += 1
    #         for key, value in repo_analysis_results["de_duplication_stats"].items(): 
    #             total_de_duplication_stats[key] += value
    # 
    # print(f"De-duplication Statistics data for {repo_count} repositories.")
    # for key, value in total_de_duplication_stats.items(): 
    #     print(f"  duplicates in {key}: {value}")    
    # print(f"Most popular Wasm modules")
    # for key, value in wasm_hashes_counter.most_common()[:10]:
    #     print(f"  {key}: {value} times")    
    # ed97339a3c2cdcd30fe7903ecad11562b7b9bfcfde24e0e584346f54c9247148: 679 times - math 
    # cd5d4935a48c0672cb06407bb443bc0087aff947c6b864bac886982c73b3027f: 518 times - empty binary 
    # be2dc7da3885e55013c8da58d7ba356705d932459db94ada37d5de2fa8733cfe: 418 times - UGH 
    # 2749fcb9988de1001c215e216230cfb2f3858ace99d15bf32ab039f5b1be3e3f: 273 times
    # f2445f0bf245875db4d6cd2b05d157e9a45e28b483b8fda344864fc0079f45bd: 220 times
    # 184dd23f46143e2a9fe19cef543e12b407d9da1f99eee2585b7c899a874e06ed: 205 times
    # 02c2db374bd846d61fef6a1ea32407e3845114b147a118a892de0eb68196ddae: 126 times
    # 93a44bbb96c751218e4c00d479e4c14358122a389acca16205b1e4d0dc5f9476: 119 times
    # fd885c2d12e5951e59d761ebd4a006e06254b1491fd6f530c92b69fb4d8d77d9: 94 times
    # bb88497dce406ea66f1867cf36044ff587f80244b609a7033547744754defee4: 91 times

def de_duplication_stats_without_empty_magic_wasm(): 
    MAGIC_WASM_START_HASH = "cd5d4935a48c0672cb06407bb443bc0087aff947c6b864bac886982c73b3027f"
    with open(DEP_ANLYSIS_JSON, 'r') as f: 
        dep_analysis_results = json.load(f)

    total_de_duplication_stats = {
        "array": 0, "base64": 0, "binary": 0, 
        "array_&_base64": 0, "array_&_binary": 0, "base64_&_binary": 0,
        "array_&_base64_&_binary": 0,
    }

    repo_count = 0 
    for repo_full_name, repo_analysis_results in dep_analysis_results.items():
        if "wasm_sources_with_hash" in repo_analysis_results: 

            repo_analysis_results = repo_analysis_results["wasm_sources_with_hash"]

            repo_analysis_results["binary"] = [i for i in repo_analysis_results["binary"] if i != MAGIC_WASM_START_HASH] 
            repo_analysis_results["array"] = [i for i in repo_analysis_results["array"] if i != MAGIC_WASM_START_HASH]
            repo_analysis_results["base64"] = [i for i in repo_analysis_results["base64"] if i != MAGIC_WASM_START_HASH]

            binary_hashes = set(repo_analysis_results["binary"])
            array_hashes = set(repo_analysis_results["array"])
            base64_hashes = set(repo_analysis_results["base64"])

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

            de_duplication_stats["array"] = len(repo_analysis_results["array"]) - len(array_hashes)
            de_duplication_stats["base64"] = len(repo_analysis_results["base64"]) - len(base64_hashes)
            de_duplication_stats["binary"] = len(repo_analysis_results["binary"]) - len(binary_hashes)
            de_duplication_stats["array_&_base64"] = len(array_hashes.intersection(base64_hashes))
            de_duplication_stats["array_&_binary"] = len(array_hashes.intersection(binary_hashes))
            de_duplication_stats["base64_&_binary"] = len(base64_hashes.intersection(binary_hashes))
            de_duplication_stats["array_&_base64_&_binary"] = len(array_hashes.intersection(base64_hashes).intersection(binary_hashes))

            for key, value in de_duplication_stats.items(): 
                total_de_duplication_stats[key] += value

    print(f"De-duplication Statistics data for {repo_count} repositories.")
    for key, value in total_de_duplication_stats.items(): 
        print(f"  duplicates in {key}: {value}")    

def pretty_print_number(n, MAX): 
    num_spaces = MAX-len(str(n))
    return f"{num_spaces*' '}{n}"

def display_freq_dist(data, MAX_PERCENT=60):    
    bins = np.logspace(np.log10(1),np.log10(max(data)), 10)
    freq_dist = pd.cut(data, bins=bins, include_lowest=True, right=False).value_counts().sort_index()
    freq_dist = freq_dist.to_dict()    
    max_bin_str_len = len(str(max([round(key.right) for key in freq_dist.keys()])))
    max_count_str_len = len(str(max(freq_dist.values())))        
    counts = freq_dist.values()
    cum_count = 0
    total_count = sum(counts)
    print(f"Min freq:{min(counts)}, Max freq:{max(counts)}")
    for bin, count in freq_dist.items(): 
        cum_count += count
        print(f"{pretty_print_number(round(bin.right), max_bin_str_len)} {pretty_print_number(count, max_count_str_len)} {pretty_print_number(round(100*(cum_count/total_count), 2), 5)}%")

def freq_dist_graph(file, data, x_label, verbose=False): 
    bins = np.logspace(np.log10(1),np.log10(max(data)), 10)
    plt.figure(figsize=(17, 10))
    plt.ylim(0, 650)
    plt.hist(data, bins)
    plt.xscale("log")    
    plt.xlabel(x_label)
    plt.savefig(file, bbox_inches='tight')
    plt.clf()  
    if verbose:
        display_freq_dist(data)
    

def package_dynamic_clients_freq(verbose=False): 
    with open(INSTANTIATION_JSON, 'r') as f: 
        package_to_client_to_instantiation_count = json.load(f)

    data = [len(item) for item in package_to_client_to_instantiation_count.values()]
    freq_dist_graph(
        file = FREQ_DIST_DYNAMIC_CLIENTS_PACKAGES, 
        data = data,
        x_label = "Number of dynamic clients of dependent packages",
        verbose=verbose
    )    

    if verbose:
        print(f"Frequency Distributon of the Number of Dynamic Clients of NPM packages at {FREQ_DIST_DYNAMIC_CLIENTS_PACKAGES}")
        print()

def wasm_hash_dynamic_clients_freq(verbose=False): 
    wasm_hash_to_num_clients = Counter()
    for repo_dir in os.listdir(DUMPED_WASM_FILES): 
        repo_dumped_wasm = os.listdir(f"./../data/dumped-wasm-files/{repo_dir}")
        if len(repo_dumped_wasm) > 0: 
            wasm_hash_to_num_clients.update(repo_dumped_wasm)
            
    data = list(wasm_hash_to_num_clients.values())
    freq_dist_graph(
        file = FREQ_DIST_DYNAMIC_CLIENTS_WASM_HASH, 
        data = data, 
        x_label = "Number of dynamic clients of WebAssembly modules", 
        verbose=verbose
    )    

    if verbose:
        print(f"Frequency Distributon of the Number of Dynamic Clients of Wasm Modules at {FREQ_DIST_DYNAMIC_CLIENTS_WASM_HASH}")
        print()

def wasm_hash_static_clients_freq(verbose=False): 
    with open(DEP_ANLYSIS_JSON, 'r') as f: 
        dep_analysis = json.load(f)
    
    wasm_hash_counter = Counter()
    for dep_result in dep_analysis.values():
        wasm_hashes = set()
        wasm_hashes.update(dep_result["wasm_sources_with_hash"]["array"]) 
        wasm_hashes.update(dep_result["wasm_sources_with_hash"]["base64"]) 
        wasm_hashes.update(dep_result["wasm_sources_with_hash"]["binary"]) 
        wasm_hash_counter.update(list(wasm_hashes))

    print(len(wasm_hash_counter.keys()))
    print(sum(wasm_hash_counter.values()))
    data = list(wasm_hash_counter.values())
    freq_dist_graph(
        file = FREQ_DIST_STATIC_CLIENTS_WASM_HASH,
        data = data,  
        x_label="Number of static clients of WebAssembly modules",
        verbose=verbose
    )

    if verbose:
        print(f"Frequency Distributon of the Number of Static Clients of Wasm Modules at {FREQ_DIST_STATIC_CLIENTS_WASM_HASH}")
        print()

def get_entries(static_info, table_id):
    for element_section in static_info['element_section']['elements']: 
            if element_section['associated_table'] == table_id: 
                unique_funcs_in_table = list(set(element_section['entries']))
                return unique_funcs_in_table
    return []         

def avg_exports_per_wasm_file(interop_wasm_modules): 

    print("QUERY: What percentage of WebAssembly exported functions are called by JavaScript?")

    with open(WASM_STATIC_INFO_JSON, 'r') as f: 
        wasm_static_info = json.load(f)
    with open(EXPORTS_CALLED_COUNT_JSON, 'r') as f: 
        package_to_client_to_wasm_to_export_count = json.load(f)

    # For every wasm file, average percentange of exports called per client
    wasm_hash_to_client_percent = {wasm_hash: [] for wasm_hash in interop_wasm_modules} 
    for package_name, package in package_to_client_to_wasm_to_export_count.items(): 
        for client_name, client in package.items():
            for wasm_hash, export_count in client.items(): 
                exports_called = list(export_count.keys())

                assert(wasm_hash in wasm_static_info)
                static_info = wasm_static_info[wasm_hash]
                
                if len(exports_called) > static_info['export_section']['count_exported_funcs'] and static_info['export_section']['count_exported_funcs'] == 0: 
                    print(f"ERROR: Wasm file {wasm_hash} in {client_name} has {len(exports_called)} but reports {static_info['exports']['count_exported_funcs']} functions exported.")
                    continue                     
                
                exported_funcs = [export['name'] for export in static_info['export_section']['exports'] if export['_type'] == 'Function']
                exports_called = [func for func in exports_called if func in exported_funcs]

                percent_exports_called = 100*(len(exports_called)/static_info['export_section']['count_exported_funcs'])
                if wasm_hash not in wasm_hash_to_client_percent: 
                    #print(f"{wasm_hash}: {percent_exports_called}% export funcs called")
                    assert(percent_exports_called == 0)
                else:
                    wasm_hash_to_client_percent[wasm_hash].append(percent_exports_called)
                

    assert(len(interop_wasm_modules) == len(wasm_hash_to_client_percent))    
    wasm_modules = np.arange(0, len(wasm_hash_to_client_percent))
    avg_client_percent_calls = [statistics.mean(client) if len(client)>0 else 0 for wasm, client in wasm_hash_to_client_percent.items()]
    avg_client_percent_calls.sort(reverse=True)

    # plot bars in stack manner
    plt.figure(figsize=(17, 10))
    plt.bar(wasm_modules, avg_client_percent_calls, color='tab:blue')    
    plt.xlabel("Wasm modules that interoperate with JavaScript")
    plt.ylabel("Mean \% exported functions called")
    plt.savefig(PERCENT_EXPORTED_FUNCS_CALLED, bbox_inches='tight')
    plt.clf()
    print(f"Exports Called Graph at {PERCENT_EXPORTED_FUNCS_CALLED}")
    print(F"{len(wasm_hash_to_client_percent)} unqiue WebAssembly Modules are interoperated with.")
    
    bins=[0, 5, 20, 40, 60, 80, 100] 
    percent_exports_called_freq_dist = pd.cut(avg_client_percent_calls, bins=bins, include_lowest=True, right=False).value_counts().sort_index()
    for interval, count in dict(percent_exports_called_freq_dist).items():
        print(f"{count} in {interval.left}-{interval.right}") 
    print(f"A Wasm Module in the dataset has a median of {statistics.median(avg_client_percent_calls):.2f}% of its exported functions called by JavaScript.") 
    print(f"A Wasm Module in the dataset has a mean of {statistics.mean(avg_client_percent_calls):.2f}% of its exported functions called by JavaScript.") 
    print()

    avg_client_percent_calls = []
    wasm_total_exported_funcs = []
    num_of_modules_ignored = 0
    for wasm_hash, client in wasm_hash_to_client_percent.items(): 
        num_exported_funcs = wasm_static_info[wasm_hash]['export_section']['count_exported_funcs']
        if num_exported_funcs > 200: 
            num_of_modules_ignored +=1
            continue
        avg_client_percent_calls.append(statistics.mean(client) if len(client)>0 else 0)
        assert(wasm_hash in wasm_static_info)
        wasm_total_exported_funcs.append(num_exported_funcs)

    print(f"{num_of_modules_ignored} modules ignored since number of exported functions > 200")
    assert(len(avg_client_percent_calls) == len(wasm_total_exported_funcs))    
    plt.figure(figsize=(17, 10))    
    plt.scatter(wasm_total_exported_funcs, avg_client_percent_calls, s=None, c=None)
    plt.xlabel("Total number of exported functions")
    plt.ylabel("Mean \% exported functions called")
    plt.savefig(SCATTER_PLOT_PERCENT_EXPORTED_FUNCS_CALLED, bbox_inches='tight')
    plt.clf()
    print(f"Scatter Plot of Exports Called at {SCATTER_PLOT_PERCENT_EXPORTED_FUNCS_CALLED}")
    print()

def calls_through_table(interop_wasm_modules):

    with open(CALLS_THROUGH_TABLE_JSON, 'r') as f: 
        package_to_client_to_calls_through_table_count = json.load(f)
    with open(WASM_STATIC_INFO_JSON, 'r') as f: 
        wasm_static_info = json.load(f)

    # For every wasm hash that has an exported table, 
    # report the avg percentage of functions in the table that have been called over all clients
    wasm_hash_to_unique_funcs_in_exposed_table = {}
    for wasm_hash in interop_wasm_modules: 
        static_info = wasm_static_info[wasm_hash]

        if wasm_hash not in wasm_hash_to_unique_funcs_in_exposed_table: 
            wasm_hash_to_unique_funcs_in_exposed_table[wasm_hash] = set()
 
        for import_ in static_info['import_section']['imports']: 
            if import_['_type'] == 'Table':                    
                # FIXME: Add table entries from imported elements?
                wasm_hash_to_unique_funcs_in_exposed_table[wasm_hash].update(
                    get_entries(static_info, import_['internal_id'])
                )
        
        for export in static_info['export_section']['exports']:
            if export['_type'] == 'Table':
                wasm_hash_to_unique_funcs_in_exposed_table[wasm_hash].update(
                    get_entries(static_info, export['internal_id'])
                )
    
    wasm_hash_to_client_percent_table_calls = {
        wasm_hash: {
            "table_size": None, 
            "client_percent_table_calls": []
        } 
        for wasm_hash in wasm_hash_to_unique_funcs_in_exposed_table
    }  
    wasm_hash_to_modified_table_calls = {}
    wasm_hash_to_funcs_in_both = {}
    for package_name, package in package_to_client_to_calls_through_table_count.items(): 
        for client_name, client in package.items(): 
            # package_to_client_to_calls_through_table_count[package_name][client_name][wasm_file]["counts"] = Counter() 
            # package_to_client_to_calls_through_table_count[package_name][client_name][wasm_file]["functions_called"] = Counter()
            for wasm_hash, calls_through_table in client.items(): 

                assert(wasm_hash in wasm_hash_to_unique_funcs_in_exposed_table)
                
                counts = calls_through_table["counts"]
                functions_called = [int(x) for x in list(calls_through_table["functions_called"].keys())]
                static_funcs_in_table = wasm_hash_to_unique_funcs_in_exposed_table[wasm_hash]
                exported_functions = [export['internal_id'] for export in wasm_static_info[wasm_hash]['export_section']['exports'] if export['_type'] == 'Function']
                
                funcs_in_static_table_called = set()
                funcs_not_in_static_table = set()
                funcs_called_also_exported = set()
                
                for func in functions_called: 
                    # Check if the functions called are in the reported static table
                    # If they aren't this table has been mutated
                    if func not in static_funcs_in_table: 
                        funcs_not_in_static_table.add(func)
                    else: 
                        funcs_in_static_table_called.add(func)

                    # Check if the functions called are only exported through the table
                    if func in exported_functions: 
                        funcs_called_also_exported.add(func)

                if len(funcs_not_in_static_table) > 0:
                    #print(f"Table has been modified: {len(funcs_not_in_static_table)} called from table in {wasm_hash} that were not present.")
                    wasm_hash_to_modified_table_calls[wasm_hash] = funcs_not_in_static_table                    

                if len(funcs_called_also_exported) >0: 
                    if wasm_hash not in wasm_hash_to_funcs_in_both: 
                        wasm_hash_to_funcs_in_both[wasm_hash] = set()
                    wasm_hash_to_funcs_in_both[wasm_hash].update(funcs_called_also_exported)

                if wasm_hash_to_client_percent_table_calls[wasm_hash]["table_size"] is None:    
                    wasm_hash_to_client_percent_table_calls[wasm_hash]["table_size"] = len(static_funcs_in_table)
                else: 
                    assert(wasm_hash_to_client_percent_table_calls[wasm_hash]["table_size"] == len(static_funcs_in_table))
                wasm_hash_to_client_percent_table_calls[wasm_hash]["client_percent_table_calls"].append(
                    100*(len(funcs_in_static_table_called)/len(static_funcs_in_table))
                    if len(funcs_in_static_table_called) > 0
                    else 0.0
                )                    

    assert(len(interop_wasm_modules) == len(wasm_hash_to_client_percent_table_calls))

    print("QUERY: Do WebAssembly Modules export the same functions in a table and explicitly?")
    print(f"{len(wasm_hash_to_funcs_in_both)} WebAssembly Modules have functions exported as a function and through an exported table.")
    print(f"A median of {statistics.median([len(funcs) for funcs in wasm_hash_to_funcs_in_both.values()]):.2f} functions are exported through both elements.")
    print() 

    print("QUERY: Does JavaScript ever invoke functions that are only exported through a table?")    
    wasm_modules = np.arange(0, len(interop_wasm_modules))
    avg_client_percent_calls = [
        statistics.mean(client_percents["client_percent_table_calls"]) if len(client_percents["client_percent_table_calls"]) > 0 else 0.0
        for client_percents in wasm_hash_to_client_percent_table_calls.values()
    ]
    avg_client_percent_calls.sort(reverse=True)
 
    # plot bars in stack manner
    plt.figure(figsize=(17, 10))
    plt.bar(wasm_modules, avg_client_percent_calls, color='tab:blue')    
    plt.xlabel("WebAssembly modules with imported or exported tables")
    plt.ylabel("Mean \% functions in table called")
    plt.savefig(PERCENT_FUNCS_IN_EXPORTED_TABLE_CALLED, bbox_inches='tight')
    plt.clf()
    print(f"Functions Called through Exported Table Graph at {PERCENT_FUNCS_IN_EXPORTED_TABLE_CALLED}")
    
    print(f"{len([percent for percent in avg_client_percent_calls if percent > 0])}/{len(interop_wasm_modules)} Wasm Modules call functions through an exported table.")
    print(f"Of these Wasm Modules, a median of {statistics.median([percent for percent in avg_client_percent_calls if percent > 0]):.2f}% of the functions in the table are called.")
    print(f"A minimum of {min(avg_client_percent_calls)}% is called and a maximum of {max(avg_client_percent_calls)}")
    print()

    # Scatter Plot of avg_percent_calls and wasm table size. 
    # wasm_table_size, avg_client_percent_calls = [], []
    # for val in wasm_hash_to_client_percent_table_calls.values():
    #     wasm_table_size.append(val["table_size"])
    #     avg_client_percent_calls.append(statistics.mean(val["client_percent_table_calls"]) if len(val["client_percent_table_calls"]) > 0 else 0)        
    # plt.scatter(wasm_table_size, avg_client_percent_calls, s=None, c=None)
    # plt.savefig('temp.pdf', bbox_inches='tight')
    # plt.clf()

    print('QUERY: What percentage of applications mutate an imported or exported WebAssembly table or other exported elements')
    wasm_modules = np.arange(0, len(wasm_hash_to_unique_funcs_in_exposed_table))
    modified_percent = []
    for wasm_hash in wasm_hash_to_unique_funcs_in_exposed_table: 
        if wasm_hash not in wasm_hash_to_modified_table_calls: modified_percent.append(0); continue
        if wasm_hash_to_client_percent_table_calls[wasm_hash]["table_size"] == 0: modified_percent.append(0); continue
        modified_percent.append(
            100*(len(wasm_hash_to_modified_table_calls[wasm_hash])/wasm_hash_to_client_percent_table_calls[wasm_hash]["table_size"])
        )
    modified_percent.sort(reverse=True)


    plt.figure(figsize=(17, 10))
    plt.bar(wasm_modules, modified_percent, color='tab:blue')    
    plt.xlabel("WebAssembly modules with imported or exported tables")
    plt.ylabel("\% of entries by which table is modified   ")
    plt.savefig(TABLE_MODIFIED_PERCENT, bbox_inches='tight')
    plt.clf()

    print(f"Number of Wasm Modules with imported/exported tables whose table is modified found in {TABLE_MODIFIED_PERCENT}")
    print(f'{len([percent for percent in modified_percent if percent > 0])}/{len(wasm_modules)} number of tables are modified.')
    modified_percent_lt_5 = [percent for percent in modified_percent if percent<5 and percent!=0]
    modified_percent_gte_5 = [percent for percent in modified_percent if percent>=5 ]
    print(f"{len(modified_percent_gte_5)} Modules have table modified more than and equal to 5% of their original size.")
    print(f"{len(modified_percent_lt_5)} Modules have table modified less than 5% of their original size, with a median of {statistics.median(modified_percent_lt_5):.2f} and a mean of {statistics.mean(modified_percent_lt_5):.2f}")
    print()


def client_variance_in_export_calls(interop_wasm_modules): 
    
    with open(WASM_STATIC_INFO_JSON, 'r') as f: 
        wasm_static_info = json.load(f)
    with open(EXPORTS_CALLED_COUNT_JSON, 'r') as f: 
        package_to_client_to_wasm_to_export_count = json.load(f)

    # Average percentange of exported functions called per client of a wasm file, 
    # if atleast one export of a wasm file is called. 
    wasm_file_to_client_percent = {}
    for package_name, package in package_to_client_to_wasm_to_export_count.items(): 
        for client_name, client in package.items():
            for wasm_hash, export_funcs_count in client.items(): 
                export_funcs_called = list(export_funcs_count.keys())
                
                if wasm_hash == "TODO": continue
                assert(wasm_hash in wasm_static_info)
                
                static_info = wasm_static_info[wasm_hash] 
                if len(export_funcs_called) > static_info['export_section']['count_exported_funcs'] and static_info['export_section']['count_exported_funcs'] == 0: 
                    print(f"ERROR: Wasm file {wasm_hash} in {client_name} has {len(export_funcs_called)} but reports {static_info['exports']['count_exported_funcs']} functions exported.")
                    continue                     

                exported_funcs = [export['name'] for export in static_info['export_section']['exports'] if export['_type'] == 'Function']
                
                #print(wasm_hash)
                #print(client_name, package_name)
                #print(f"NUM_EXPORTED_FUNCS={exported_funcs}")
                #print(f"FUNCS_CALLED={export_funcs_called}")
                #print(f"FUNCS_NOT_CALLED={list(funcs_not_called)}")
                #print()

                #print(f"{len(exported_funcs)} {len(export_funcs_called)}")
                #print(exported_funcs)
                #print(export_funcs_called)

                assert(len(exported_funcs) >= len(export_funcs_called))
                # Below assert should hold 
                #for func in export_funcs_called:                 
                #    assert(func in exported_funcs)
                export_funcs_called = [func for func in export_funcs_called if func in exported_funcs]
                
                funcs_not_called = set(exported_funcs).difference(set(export_funcs_called))
                
                percent_exports_called = 100*(len(export_funcs_called)/static_info['export_section']['count_exported_funcs'])
                assert(percent_exports_called <= 100) 

                if wasm_hash not in wasm_file_to_client_percent: 
                    wasm_file_to_client_percent[wasm_hash] = []                
                                
                wasm_file_to_client_percent[wasm_hash].append({
                    "client_name": client_name, 
                    "num_exports": len(set(exported_funcs)),
                    "exported_funcs": list(set(exported_funcs)), 
                    "percent_exports_called": percent_exports_called, 
                    "functions_called": export_funcs_called, 
                    "functions_not_called": list(funcs_not_called)
                })

    # We have wasm_hash to list of client percentages of exported functions called. 
    # We want to now report on how many of these hashes clients have the calls to the same functions 
    # We want to report on how many of these hashes clients call different functions  
    wasm_hash_with_same_client_calls = {}
    wasm_hash_with_diff_client_calls = set()
    wasm_hash_with_one_client = set()
    for wasm_hash in wasm_file_to_client_percent:     
        client_names = set([client["client_name"] for client in wasm_file_to_client_percent[wasm_hash]])
        clients_funcs_called = [client["functions_called"] for client in wasm_file_to_client_percent[wasm_hash]]        
        if len(client_names) == 1: 
            wasm_hash_with_one_client.add(wasm_hash)
        # If all clients call the same set of functions 
        elif set(clients_funcs_called[0]) == set([func for client_funcs in clients_funcs_called for func in client_funcs]): 
            wasm_hash_with_same_client_calls[wasm_hash] = list(client_names)
        else: 
            #print(f"Client functions called {clients_funcs_called} for {wasm_hash}")
            wasm_hash_with_diff_client_calls.add(wasm_hash)
            
    print(f"{len(wasm_hash_with_one_client) + len(wasm_hash_with_same_client_calls) + len(wasm_hash_with_diff_client_calls)} WebAssembly Modules have calls via exported functions.")               
    print(f"{len(wasm_hash_with_one_client)} have one client.")
    print(f"{len(wasm_hash_with_same_client_calls)} have same calls from clients.")
    print(f"{len(wasm_hash_with_diff_client_calls)} have different calls from clients.")
    print()
    
    #print("Wasm hashes with same set of calls from clients (capped at 5): ")
    #for count, (wasm_hash, clients) in enumerate(wasm_hash_with_same_client_calls.items()): 
    #    if count == 5: break
    #    print(f"  {wasm_hash}: {clients}")
    #print()
    
    #print("Wasm hashes with different set of calls from clients:")
    #for wasm_hash in wasm_hash_with_diff_client_calls:
    #    print(f"  {wasm_hash}")#: {[client['functions_called'] for client in wasm_file_to_client_percent[wasm_hash]]}")
    #print()
    
    print('QUERY: What percentage of exported functions in a Wasm binary are never called by any client?')
    wasm_modules = np.arange(0, len(interop_wasm_modules))    
    percent_funcs_not_called = [
        100*(
            len(
                set.intersection(*[set(client["functions_not_called"]) for client in wasm_file_to_client_percent[wasm_hash]])
                )/
            wasm_file_to_client_percent[wasm_hash][0]["num_exports"]
        ) 
        if wasm_hash in wasm_file_to_client_percent else 100
        for wasm_hash in interop_wasm_modules
    ]        
    percent_funcs_not_called.sort(reverse=True)

    plt.figure(figsize=(17, 10))
    plt.bar(wasm_modules, percent_funcs_not_called, color='tab:blue')
    plt.xlabel("Wasm modules that interoperate with JavaScript")
    plt.ylabel("% Exported functions never called")
    plt.savefig(EXPORTS_NEVER_CALLED, bbox_inches='tight')
    plt.clf()

    print(f"Wasm Modules whose exports are never called found in {EXPORTS_NEVER_CALLED}")
    print()

def instantiation_type_bar_chart(): 

    print("QUERY: What percentage of WebAssembly modules are instantiated via streaming, buffer and synchronously?")

    with open(INSTANTIATION_JSON, 'r') as f: 
        package_to_client_to_instantiation_count = json.load(f)

    package_to_avg_client_instantiation = {}

    for package in package_to_client_to_instantiation_count: 
        total_client_instantiateStreaming_percent, total_client_instantiate_percent, total_client_Instance_percent = 0, 0, 0
        num_clients = len(package_to_client_to_instantiation_count[package])
        for client in package_to_client_to_instantiation_count[package]: 
            total_instantiation = sum(package_to_client_to_instantiation_count[package][client].values()) 
            if total_instantiation == 0: 
                continue 
            total_client_instantiateStreaming_percent += 100*(
                (package_to_client_to_instantiation_count[package][client]["WebAssemblyInstantiateStreaming"] 
                if "WebAssemblyInstantiateStreaming" in package_to_client_to_instantiation_count[package][client]
                else 0 
                )/total_instantiation)
            total_client_instantiate_percent += 100*(
                (package_to_client_to_instantiation_count[package][client]["WebAssemblyInstantiate"]
                if "WebAssemblyInstantiate" in package_to_client_to_instantiation_count[package][client]
                else 0 
                )/total_instantiation)
            total_client_Instance_percent += 100*(
                (package_to_client_to_instantiation_count[package][client]["WebAssemblyInstance"]
                if "WebAssemblyInstance" in package_to_client_to_instantiation_count[package][client]
                else 0                 
                )/total_instantiation)

        package_to_avg_client_instantiation[package] = {
            "num_clients": num_clients,
            "instantiateStreaming": total_client_instantiateStreaming_percent / num_clients,
            "instantiate": total_client_instantiate_percent / num_clients,
            "Instance": total_client_Instance_percent / num_clients            
        }            
                    
    # Sort the packages based on avg client percent 
    package_to_avg_client_instantiation = {package: inst_avg 
        for package, inst_avg in sorted(
            package_to_avg_client_instantiation.items(), 
            key=lambda item: item[1]["Instance"] + item[1]["instantiate"] + item[1]["instantiateStreaming"], 
            reverse=True
    )}

    # What percentage of NPM packages always instantiate a Wasm module? 
    #  How many of those have only one client?
    # What is the distribution over number of clients for a NPM package?   
    NPM_packages_100_inst = Counter()
    NPM_packages_less_100_inst_count = 0 
    NPM_packages_less_100_inst = []     
    for val in package_to_avg_client_instantiation.values():
        total_avg = val["Instance"] + val["instantiate"] + val["instantiateStreaming"]
        if total_avg == 100: 
            NPM_packages_100_inst.update([val["num_clients"]])
        elif total_avg > 0: 
            NPM_packages_less_100_inst_count += 1 
            NPM_packages_less_100_inst.append(val["num_clients"])


    print(f"{sum(NPM_packages_100_inst.values())} NPM packages clients always instantiate a WebAssembly Module.")
    print("Of these,")
    for k, count in NPM_packages_100_inst.most_common(): 
        print(f"  {count} NPM packages have {k} clients.")

    bins=[1,2,3,4,5,10,20,50,100] 
    clients_freq_dist_less_100 = pd.cut(NPM_packages_less_100_inst, bins=bins, include_lowest=True, right=False).value_counts().sort_index()
    print(f"{NPM_packages_less_100_inst_count} NPM packages clients instantiate a WebAssembly Module between 0 and 100 times.")
    print("Of these, this is how the number of clients distribute")
    #print(clients_freq_dist_less_100)

    total = 0 
    calls_to_instance = 0 
    calls_to_instantate = 0
    calls_to_instantateStreaming = 0 
    for p in package_to_avg_client_instantiation: 
        calls_to_instance += package_to_avg_client_instantiation[p]["Instance"] 
        calls_to_instantate += package_to_avg_client_instantiation[p]["instantiate"] 
        calls_to_instantateStreaming += package_to_avg_client_instantiation[p]["instantiateStreaming"]
        total += package_to_avg_client_instantiation[p]["Instance"] + package_to_avg_client_instantiation[p]["instantiate"] + package_to_avg_client_instantiation[p]["instantiateStreaming"]
    print(f"Portion of calls to Instance() {100*(calls_to_instance/total):.2f}")    
    print(f"Portion of calls to instantiate(): {100*(calls_to_instantate/total):.2f}")    
    print(f"Portion of calls to instantiateStreaming(): {100*(calls_to_instantateStreaming/total):.2f}")    

    # create data
    package_names = np.arange(0, len(package_to_avg_client_instantiation))
    instance = np.array([package_to_avg_client_instantiation[p]["Instance"] for p in package_to_avg_client_instantiation])
    instantiate = np.array([package_to_avg_client_instantiation[p]["instantiate"] for p in package_to_avg_client_instantiation])
    instantiateStreaming = np.array([package_to_avg_client_instantiation[p]["instantiateStreaming"] for p in package_to_avg_client_instantiation])

    # plot bars in stack manner
    plt.figure(figsize=(17, 10))
    plt.bar(package_names, instance, color='tab:red')
    plt.bar(package_names, instantiate, bottom=instance, color='tab:blue')
    plt.bar(package_names, instantiateStreaming, bottom=instance+instantiate, color='tab:green')

    plt.xlabel("Packages")
    plt.ylabel("Mean \% instantiation per client")
    plt.legend(["WebAssembly.Instance()", "WebAssembly.instantiate()", "WebAssembly.instantiateStreaming()"])
    plt.savefig(INSTANTIATION_GRAPH_FILE, bbox_inches='tight')
    plt.clf()

    print(f"Instantiation Graph at {INSTANTIATION_GRAPH_FILE}")
    print()


def init_no_interop(verbose=False): 
    # For each wasm hash, number of clients it is instantiated in, vs, interoperated with 
    if verbose: 
        print("QUERY: Out of all binaries that are instantiated, how many of them do not show any interoperation with JavaScript?")
    
    with open(WASM_MODULES_INTEROP_TYPE, 'r') as f: 
        wasm_modules_interop_type = json.load(f)

    wasm_hash_to_clients_init_and_interop = {}
    wasm_hash_to_percent_calls_through_table = {}   
    for wasm_hash, client in wasm_modules_interop_type.items():
        
        wasm_hash_to_clients_init_and_interop[wasm_hash] = {
            "init": set(), 
            "interop": set()
        }
        for client_name, package in client.items():
            for package_name, interop_type_counter in package.items(): 
                interop_types = interop_type_counter['interop_type'].keys()
                if 'Init' in interop_types: 
                    wasm_hash_to_clients_init_and_interop[wasm_hash]["init"].update(client)
                if 'Init' in interop_types and ("CallExportedFunc" in interop_types or "CallFuncInExportTable" in interop_types):                     
                    func_calls = interop_type_counter['interop_type']["CallExportedFunc"] if "CallExportedFunc" in interop_types else 0  
                    table_calls = interop_type_counter['interop_type']["CallFuncInExportTable"] if "CallFuncInExportTable" in interop_types else 0  
                    if wasm_hash not in wasm_hash_to_percent_calls_through_table: 
                        wasm_hash_to_percent_calls_through_table[wasm_hash] = []     
                    wasm_hash_to_percent_calls_through_table[wasm_hash].append(100*(table_calls/(table_calls+func_calls)))
                    wasm_hash_to_clients_init_and_interop[wasm_hash]["interop"].update(client)
    
    init_only_wasm_modules = [wasm_hash 
        for wasm_hash, obj in wasm_hash_to_clients_init_and_interop.items()        
        if len([client for client in obj['init'] if client not in obj['interop']]) > 0 
    ]
    interop_wasm_modules = [wasm_hash for wasm_hash, obj in wasm_hash_to_clients_init_and_interop.items() if len(obj['interop']) > 0]
    
    num_only_init_wasm_modules = len(init_only_wasm_modules)
    num_interop_wasm_modules = len(interop_wasm_modules)
    assert(num_only_init_wasm_modules + num_interop_wasm_modules == len(wasm_hash_to_clients_init_and_interop))

    if verbose: 
        print(f"{len(wasm_hash_to_clients_init_and_interop)} number of unique wasm modules are instantiated.")
        print(f"{num_interop_wasm_modules} number of wasm modules are interoperate with JavaScript clients.")
        print(f"{num_only_init_wasm_modules} number of wasm modules are instantiated and never interoperated with.")

    wasm_hashes = np.arange(0, len(interop_wasm_modules))
    avg_percent_calls = []
    for client_percent_table_calls in sorted(wasm_hash_to_percent_calls_through_table.values(), reverse=True):        
        percent_table_calls = statistics.mean(client_percent_table_calls) if len(client_percent_table_calls)>0 else 0 
        if percent_table_calls > 100: 
            print(client_percent_table_calls)
        avg_percent_calls.append((percent_table_calls, 100 - percent_table_calls)) 
    
    avg_percent_calls.sort(key=lambda percent: percent[1])
    avg_percent_table_calls = [percent[0] for percent in avg_percent_calls]
    avg_percent_funcs_calls = [percent[1] for percent in avg_percent_calls]
    assert(len(avg_percent_calls) == len(interop_wasm_modules))
    
    plt.figure(figsize=(17, 10))
    plt.bar(wasm_hashes, avg_percent_table_calls, color='tab:blue')
    plt.bar(wasm_hashes, avg_percent_funcs_calls, bottom=avg_percent_table_calls, color='tab:orange')    

    plt.xlabel("WebAssembly modules with imported or exported tables")
    plt.ylabel("Fraction of calls via functions vs table  ")
    plt.legend(["Calls through Exported Table", "Calls through Exported Functions"])
    plt.savefig(CALLS_THROUGH_TAB_VS_FUNC, bbox_inches='tight')
    plt.clf()

    if verbose: 
        print(f"Percent Calls through Table vs Exported Functions at {CALLS_THROUGH_TAB_VS_FUNC}")
        print(f"{len([percent for percent in avg_percent_table_calls if percent > 50])} Modules have more than 50% calls via the exported table.")
        print()

    return (list(wasm_hash_to_clients_init_and_interop.keys()), interop_wasm_modules)


def table_offset_init(init_wasm_modules):     
    print("QUERY: What values are the offsets into a WebAssembly function table initialized with?")

    with open(WASM_STATIC_INFO_JSON, "r") as f: 
        wasm_static_info = json.load(f)
    with open(WASM_IMPORTS_JSON, "r") as f: 
        wasm_imports = json.load(f)

    wasm_hashes_with_imp_offset_to_global_var = {}
    wasm_hashes_with_static_offset = set()

    # For each wasm module whose table is set with an imported variable, 
    # report on the client variance of the value of the imported variable  
    for wasm_hash in init_wasm_modules: 
        assert(wasm_hash in wasm_static_info)
        static_info = wasm_static_info[wasm_hash]
        offset_var_ids = [] 
        for element in static_info['element_section']['elements']: 
            for offset in element['offsets']:                           
                assert(len(offset) == 1 and list(offset.keys())[0] in ['Global', 'Constant'])
                if 'Global' in offset: 
                    offset_var_ids.append(offset['Global']['global_index'])
                elif 'Constant' in offset: 
                    wasm_hashes_with_static_offset.add(wasm_hash)
            
        for _import in static_info['import_section']['imports']: 
            if _import['_type'] == 'Global' and _import['internal_id'] in offset_var_ids : 
                if wasm_hash not in wasm_hashes_with_imp_offset_to_global_var: 
                    wasm_hashes_with_imp_offset_to_global_var[wasm_hash] = [] 
                wasm_hashes_with_imp_offset_to_global_var[wasm_hash].append(
                    (_import['module'], _import['name'])
                ) 
    
    print(f"{len(wasm_hashes_with_static_offset)}/{len(init_wasm_modules)} Wasm Modules have static table offsets")
    print(f"{len(wasm_hashes_with_imp_offset_to_global_var)}/{len(init_wasm_modules)} Wasm Modules have imported table offsets.")

    wasm_hash_to_table_offset_values = {} 
    for wasm_hash, imported_vars in wasm_hashes_with_imp_offset_to_global_var.items():
        for (module, name) in imported_vars: 
            values_of_table_base = []
            for client, imports in wasm_imports[wasm_hash].items(): 
                assert(imports[module][name][0] == 'Number')
                values_of_table_base.append(int(imports[module][name][1]))                 
            wasm_hash_to_table_offset_values[f"{wasm_hash}__{0}"] = values_of_table_base

    print("Offset values of tables")
    for wasm_hash, offset_values in wasm_hash_to_table_offset_values.items(): 
        print(f"  - {wasm_hash}: {offset_values}")
    print()

def run_metadce(options, wasm_binary_path, reachability_graph_path, dce_binary_path): 
    metadce_result = run(shlex.split(f"{METADCE_BIN} {' '.join(options)} --dce {wasm_binary_path} --graph-file {reachability_graph_path} --output {dce_binary_path}"), check=False)                
    if metadce_result.returncode == 0:
        metadce_unused_re = re.compile("unused\: ")
        removed_functions = [metadce_unused_re.match(output) is not None for output in metadce_result.stdout.split("\n")].count(True)
        dce_binary_size = os.path.getsize(dce_binary_path)
        return (True, (dce_binary_size, removed_functions))
    else: 
        return (False, metadce_result.stderr)

def run_debloat_on_binary(
        wasm_binary_path, 
        wasm_binary_size, 
        reachability_graph_path, 
        dce_binary_path, 
        wasm_static_info, 
        exports_called, 
        calls_through_table, 
        options = []
    ):

    # Generate reachablity graph - make called exports reachable.
    # Make called exports reachable  
    reachability_graph = []
    for export in wasm_static_info["export_section"]["exports"]: 
        if (export["_type"] == "Memory" or 
            (calls_through_table and export["_type"] == "Table") or 
            (export["_type"] == "Function" and export["name"] in exports_called)): 
            reachability_graph.append({
                'name': export['name'],
                'root': True,
                'export': export['name']
            })

    with open(reachability_graph_path, 'w') as reachable_graph_f: 
        json.dump(reachability_graph, reachable_graph_f, indent=2)

    while True: 
        (success, result) = run_metadce(
            options=options, 
            wasm_binary_path=wasm_binary_path, 
            reachability_graph_path=reachability_graph_path, 
            dce_binary_path=dce_binary_path,                     
        )

        if success: 
            (dce_binary_size, removed_functions) = result
            percentage_size_decrease = 100*((wasm_binary_size - dce_binary_size)/wasm_binary_size)
            return ({
                "percent_exports_called": 100*(len(exports_called)/wasm_static_info['export_section']['count_exported_funcs']), 
                "num_exports_called": len(exports_called),
                "dce_binary_size": dce_binary_size,
                "percentage_size_decrease": percentage_size_decrease,
                "removed_functions": removed_functions,
            }, options)
        else: 
            stderr = result
            if "SIMD operations require SIMD" in stderr: 
                options.append("--enable-simd")
                continue
            elif "Bulk memory operations require bulk memory" in stderr:
                options.append("--enable-bulk-memory") 
                continue
            elif "all used features should be allowed" in stderr: 
                options.append("--all-features") 
                continue
            else: 
                stderr = result
                return ({
                    "FAILURE": "MetaDCE error",
                    "stderr": stderr
                }, options)

def get_baseline_wasm_binary(wasm_binary_path, output_dir, static_info): 
    reachability_graph = []
    reachability_graph_path = f"{output_dir}/baseline-reachability_graph.json"
    baseline_wasm_binary = f"{output_dir}/baseline-bin.wasm"
    for export in static_info["export_section"]["exports"]: 
        reachability_graph.append({
            'name': export['name'],
            'root': True,
            'export': export['name']
        })
    with open(reachability_graph_path, 'w') as reachable_graph_f: 
        json.dump(reachability_graph, reachable_graph_f, indent=2)
    options = []
    while True: 
        metadce_result = run(shlex.split(f"{METADCE_BIN} {' '.join(options)} {wasm_binary_path} --graph-file {reachability_graph_path} --output {baseline_wasm_binary}"), check=False)
        if metadce_result.returncode == 0: 
            return baseline_wasm_binary
        else: 
            if "SIMD operations require SIMD" in metadce_result.stderr: 
                options.append("--enable-simd")
                continue
            elif "Bulk memory operations require bulk memory" in metadce_result.stderr:
                options.append("--enable-bulk-memory") 
                continue
            elif "all used features should be allowed" in metadce_result.stderr: 
                options.append("--all-features") 
                continue
            else: 
                print(metadce_result.stderr)
                return None 

def run_debloat_experiment(interop_wasm_modules): 

    with open(WASM_STATIC_INFO_JSON, 'r') as f: 
        wasm_static_info = json.load(f)
    with open(EXPORTS_CALLED_COUNT_JSON, 'r') as f: 
        package_to_client_to_wasm_to_export_count = json.load(f)
    with open(CALLS_THROUGH_TABLE_JSON, 'r') as f: 
        package_to_client_to_calls_through_table_count = json.load(f)

    wasm_hash_to_dce_stats = {} 

    # For every wasm file, average percentange of exports called per client
    for package_name, package in package_to_client_to_wasm_to_export_count.items(): 
        for client_name, client in package.items():
            for wasm_hash, export_count in client.items(): 
                
                if wasm_hash not in interop_wasm_modules: continue 
                exports_called = list(export_count.keys())

                assert(wasm_hash in wasm_static_info)
                static_info = wasm_static_info[wasm_hash]
                
                if len(exports_called) > static_info['export_section']['count_exported_funcs'] and static_info['export_section']['count_exported_funcs'] == 0: 
                    print(f"ERROR: Wasm file {wasm_hash} in {client_name} has {len(exports_called)} but reports {static_info['exports']['count_exported_funcs']} functions exported.")
                    continue                     
                
                exported_funcs = [export['name'] for export in static_info['export_section']['exports'] if export['_type'] == 'Function']
                exports_called = [func for func in exports_called if func in exported_funcs]
                                 
                calls_through_table = package_to_client_to_calls_through_table_count[package_name][client_name][wasm_hash]["counts"] is dict if wasm_hash in package_to_client_to_calls_through_table_count[package_name][client_name] else False                  

                client_name_path_safe = "__".join(client_name.split("/"))
                wasm_binary_path = f"{DUMPED_WASM_FILES}/{client_name_path_safe}/realwasm-module-{wasm_hash}.wasm"
                assert(os.path.isfile(wasm_binary_path))

                output_dir = f"{DEBLOAT_BINS_DIR}/{wasm_hash}"
                if not os.path.isdir(output_dir): 
                    run(['mkdir', '-p', output_dir])

                output_dir = f"{DEBLOAT_BINS_DIR}/{wasm_hash}/{client_name_path_safe}"
                if not os.path.isdir(output_dir): 
                    run(['mkdir', '-p', output_dir])
 
                wasm_hash_to_dce_stats[wasm_hash] = {}
                
                wasm_binary_size = os.path.getsize(wasm_binary_path)
                if "wasm_binary_size"  in wasm_hash_to_dce_stats[wasm_hash]: 
                    assert(wasm_hash_to_dce_stats[wasm_hash]["wasm_binary_size"] == wasm_binary_size)
                else:                     
                    wasm_hash_to_dce_stats[wasm_hash]["wasm_binary_size"] = wasm_binary_size
                    wasm_hash_to_dce_stats[wasm_hash]["num_exported_funcs"] = len(exported_funcs)
                    

                wasm_hash_to_dce_stats[wasm_hash]["clients"] = {}
                wasm_hash_to_dce_stats[wasm_hash]["clients"][client_name] = {}
                
                # Run debloat experiment with all exports reachable.
                options = []
                (result, options) = run_debloat_on_binary(
                    wasm_binary_path,
                    wasm_binary_size=wasm_binary_size, 
                    reachability_graph_path = f"{output_dir}/all-exports-reachability_graph.json", 
                    dce_binary_path = f"{output_dir}/all-exports-dce.wasm", 
                    wasm_static_info = static_info, 
                    exports_called = exported_funcs, 
                    calls_through_table=calls_through_table, 
                    options = options 
                )                
                wasm_hash_to_dce_stats[wasm_hash]["clients"][client_name]["baseline"] = result
                    
                # Run debloat experiment with subset of exports reachable.
                (result, options) = run_debloat_on_binary(
                    wasm_binary_path, 
                    wasm_binary_size=wasm_binary_size, 
                    reachability_graph_path = f"{output_dir}/called-exports-reachability_graph.json", 
                    dce_binary_path = f"{output_dir}/called-exports-dce.wasm", 
                    wasm_static_info = static_info, 
                    exports_called = exports_called, 
                    calls_through_table=calls_through_table, 
                    options = options 
                )                
                wasm_hash_to_dce_stats[wasm_hash]["clients"][client_name]["called-exports"] = result
                    
    with open(DCE_STATS, 'w') as f: 
        json.dump(wasm_hash_to_dce_stats, f, ensure_ascii=False, indent=2)

def debloat_graph(): 
    
    with open(DCE_STATS, 'r') as f: 
        dce_stats = json.load(f)
    
    graph_data = {}
    for wasm_hash, data in dce_stats.items(): 
        if len(data.keys()) == 0: 
            continue
        percent_funcs_called, size_reduction = [], []
        for client_name, stats in data["clients"].items(): 
            if "FAILURE" in stats["baseline"]: 
                continue 
            percent_funcs_called.append(stats["called-exports"]["percent_exports_called"])                
            baseline_size = stats["baseline"]["dce_binary_size"]
            real_size = stats["called-exports"]["dce_binary_size"]
            size_reduction.append(100*((baseline_size-real_size)/baseline_size))

        graph_data[wasm_hash] = {
            "avg_percent_funcs_called": statistics.mean(percent_funcs_called) if len(percent_funcs_called) > 0 else 0, 
            "avg_size_reduction": statistics.mean(size_reduction) if len(size_reduction) > 0 else 0,
        }        

    graph_data = {k: v for k, v in sorted(graph_data.items(), key=lambda item: item[1]["avg_percent_funcs_called"], reverse=True)}    

    avg_percent_funcs_called, avg_percent_size_reduction = [], [], []
    for values in graph_data.values():
        avg_percent_funcs_called.append(values["avg_percent_funcs_called"])
        avg_percent_size_reduction.append(values["avg_size_reduction"])

    wasm_modules = np.arange(0, len(graph_data))
    plt.figure(figsize=(17, 10))
    plt.bar(wasm_modules, avg_percent_funcs_called, color='tab:blue')    
    plt.bar(wasm_modules, avg_percent_size_reduction, color='tab:orange')    
    plt.xlabel("Wasm modules that interoperate with JavaScript.")
    plt.legend(["Mean \% exports called", "Mean \% client-specific \n reduction wrt baseline size"], bbox_to_anchor=(0.35,0.8), loc="center", framealpha=0.9)
    plt.savefig(DCE_GRAPH, bbox_inches='tight')
    plt.clf()


def str_to_date(s: str) -> datetime.date: 
    return datetime.datetime.strptime(s, "%Y-%m-%d").date()


def wasm_evolution(): 

    def pattern_stats(): 
        def percent(x: int) -> float: 
            return round(100*(x/total_package_count), 2)
        print(f"Switched from JS to Wasm                    ({switch_js_wasm_count}/{total_package_count}) {percent(switch_js_wasm_count)}")
        print(f"Different version without Wasm in Fork      ({without_wasm_fork_count}/{total_package_count}) {percent(without_wasm_fork_count)}")
        print(f"Started out with Wasm from the beginning    ({from_beginning_wasm_count}/{total_package_count}) {percent(from_beginning_wasm_count)}")
        print(f"Wasm added for WebAssembly support          ({wasm_for_support_count}/{total_package_count}) {percent(wasm_for_support_count)}")
        print(f"Wasm is a port of a C/C++/Rust library      ({port_of_lib_count}/{total_package_count}) {percent(port_of_lib_count)}")
        print(f"Wasm used in static version of yarn         ({static_yarn_count}/{total_package_count}) {percent(static_yarn_count)}")

    def plot_three_libraries(): 

        def plot_two_timelines_at(y, ax, package_name, package_updates, library_updates, security_updates, first=False): 

            
            ax.text(#min_date + datetime.timedelta(days=50), 
                    max_date - datetime.timedelta(days=120),
                    y+0.25, package_name, #fontsize=20, fontstyle="italic", 
                    c="black", ha="right") 

            dot_size = 120*2

            ax.axhline(y, xmin=0.05, xmax=0.95, c="orange", zorder=1)    
            ax.scatter(x=package_updates, y=np.array([y]*len(package_updates)), s=dot_size, c="orange", zorder=2, label="Update of Wasm in package." if first else "")

            ax.axhline(y-0.5, xmin=0.05, xmax=0.95, c="blue", zorder=1)    
            ax.scatter(x=library_updates, y=np.array([y-0.5]*len(library_updates)), s=dot_size, c="navy", zorder=2, label="Update of original C/Rust library." if first else "")


            stem_data = [ date if date in security_updates else None for date in library_updates ]
            markerline, stemline, _ = ax.stem(
                stem_data, 
                np.array([y-0.5]*len(library_updates)), 
                basefmt=" ", 
                bottom = y-0.7,
                label="Security update." if first else ""        
            )        
            plt.setp(markerline, color='red', markersize = 10)
            plt.setp(stemline, color='red', linewidth=3)

        def get_data_for_package(package_data): 
            last_update_dates = [
                str_to_date(date)            
                for date in package_data["does_wasm_get_updated"]["last_update_date"]
            ]
            library_updates = [
                str_to_date(date)
                for date in package_data["does_wasm_get_updated"]["last_update_of_original_library"]
            ]        
            security_updates = [
                str_to_date(date)
                for date in package_data["does_wasm_get_updated"]["security_updates"]
            ] if "security_updates" in package_data["does_wasm_get_updated"].keys() else [] 
            library_updates += [date for date in security_updates if date not in library_updates]

            return (last_update_dates, library_updates, security_updates)
        
        packages = ["darkforest-eth/client", "yisibl/resvg-js"]  # "iden3/snarkjs"
        last_update_dates_0, library_updates_0, security_updates_0 = get_data_for_package(wasm_evolution[packages[0]])
        last_update_dates_1, library_updates_1, security_updates_1 = get_data_for_package(wasm_evolution[packages[1]])
        #last_update_dates_2, library_updates_2, security_updates_2 = get_data_for_package(wasm_evolution[packages[2]])
        all_dates = last_update_dates_0 + library_updates_0 + last_update_dates_1 + library_updates_1 #+ last_update_dates_2 + library_updates_2   
        
        fig, ax = plt.subplots(figsize=(17, 10), constrained_layout=True)
        min_date = datetime.date(np.min(all_dates).year - 1, np.min(all_dates).month, np.min(all_dates).day)
        max_date = datetime.date(np.max(all_dates).year + 1, np.max(all_dates).month, np.max(all_dates).day)
        ax.set_ylim(-4, 4)
        ax.set_xlim(min_date, max_date)
        
        plot_two_timelines_at(-1.25, ax, packages[0], last_update_dates_0, library_updates_0, security_updates_0, first=True)
        plot_two_timelines_at(1.25, ax, packages[1], last_update_dates_1, library_updates_1, security_updates_1)
        #plot_two_timelines_at(2.5, ax, packages[2], last_update_dates_2, library_updates_2, security_updates_2)

        ax.set_yticks([])
        
        ax.legend(loc="upper left", fancybox=True, framealpha=1)
        plt.savefig(WASM_EVOLUTION_GRAPH, bbox_inches='tight')
        plt.clf()
    
    with open(WASM_EVOLUTION_JSON, 'r') as f: 
        wasm_evolution = json.load(f)
    total_package_count = len(wasm_evolution)

    switch_js_wasm_count = 0        # "Switched from JS to Wasm"
    without_wasm_fork_count = 0     # "Different version without Wasm in Fork"
    from_beginning_wasm_count  = 0  # "Started out with Wasm from the beginning"
    wasm_for_support_count = 0      # "Wasm added for WebAssembly support" 
    port_of_lib_count = 0           # "Wasm is a port of a C/C++/Rust library"
    static_yarn_count = 0           # "Wasm used in static version of yarn"
    intro_dates: list[datetime.date] = []

    for package, package_data in wasm_evolution.items(): 

        if package_data["patterns"]["Switched from JS to Wasm"]: 
            switch_js_wasm_count +=1
        if package_data["patterns"]["Different version without Wasm in Fork"]: 
            without_wasm_fork_count +=1
        if package_data["patterns"]["Started out with Wasm from the beginning"]: 
            from_beginning_wasm_count +=1
        if package_data["patterns"]["Wasm added for WebAssembly support"]: 
            wasm_for_support_count +=1
        if package_data["patterns"]["Wasm is a port of a C/C++/Rust library"]: 
            port_of_lib_count +=1
        if package_data["patterns"]["Wasm used in static version of yarn"]: 
            static_yarn_count +=1

        if package_data["wasm_introduction"] is not None:
            if package_data["wasm_introduction"] != "TODO":         
                intro_dates.append(str_to_date(package_data["wasm_introduction"]["date"]))

        updated_huh = package_data["does_wasm_get_updated"]
        if updated_huh is not None and updated_huh is not False and type(updated_huh) is dict: 
            library_updates = [
                str_to_date(date)
                for date in package_data["does_wasm_get_updated"]["last_update_of_original_library"]
            ]        
            security_updates = [
                str_to_date(date)
                for date in package_data["does_wasm_get_updated"]["security_updates"]
            ] if "security_updates" in package_data["does_wasm_get_updated"].keys() else [] 

            library_updates += [date for date in security_updates if date not in library_updates]


    pattern_stats()
    plot_three_libraries()

    false_does_wasm_get_updated = 0 
    null_does_wasm_get_updates = 0 
    true_does_wasm_get_updated_num_wasm_updates = [] 
    true_does_wasm_get_updated_num_libary_updates = [] 
    for package, package_data in wasm_evolution.items(): 
        does_wasm_get_updated = package_data["does_wasm_get_updated"]
        if does_wasm_get_updated is None: 
            null_does_wasm_get_updates += 1 
        elif not does_wasm_get_updated: 
            false_does_wasm_get_updated += 1 
        else: 
            if type(does_wasm_get_updated) is dict :
                true_does_wasm_get_updated_num_wasm_updates.append(len(does_wasm_get_updated["last_update_date"]))
                true_does_wasm_get_updated_num_libary_updates.append(len(does_wasm_get_updated["last_update_of_original_library"]))

    print(f"We could match up the wasm depended upon a package with a certain library for {len(wasm_evolution)-null_does_wasm_get_updates} packages.")
    print(f"Of these {false_does_wasm_get_updated} packages do NOT update their WebAssembly binaries.")
    print(f"Of the remaining {len(wasm_evolution)-null_does_wasm_get_updates-false_does_wasm_get_updated} packages that update their binaries atleast once, the Wasm binary is updated an average of {statistics.mean(true_does_wasm_get_updated_num_wasm_updates)} while the original library is updated {statistics.mean(true_does_wasm_get_updated_num_libary_updates)} times.")


if __name__ == "__main__":

    run(['mkdir', '-p', GRAPH_DIR])
    parser = argparse.ArgumentParser(description="Collect dynamic results")
    parser.add_argument("--dynamic", action='store_true', required=False, help="Show graphs and stats of dynamic evaluation.")
    parser.add_argument("--dependency", action='store_true', required=False, help="SHow graphs and stats of dependency analysis.")
    parser.add_argument("--dataset", action='store_true', required=False, help="Show stats of dataset collection.")
    parser.add_argument("--metadce", action='store_true', required=False, help="Run debloating experiment with metadce and show results.")
    parser.add_argument("--evolution", action='store_true', required=False, help="Show results of tracking Wasm evolution and updates.")
    
    args = parser.parse_args()
    DYNAMIC = args.dynamic
    DEPENDENCY = args.dependency
    DATASET = args.dataset
    METADCE = args.metadce
    EVOLUTION = args.evolution

    with open(WASM_MODULES_INTEROP_TYPE, "r") as f: 
        interop_type = json.load(f)

    if DATASET: 
        general_dataset_stats()

    if DEPENDENCY: 
        answer_package_dependency_research_questions()
        wasm_source_graph()
        de_duplication_stats()
        # de_duplication_stats_without_empty_magic_wasm()

    if DYNAMIC:
        (init_wasm_modules, interop_wasm_modules) = init_no_interop(verbose=True)

        package_dynamic_clients_freq(verbose=True)
        wasm_hash_static_clients_freq(verbose=True)
        wasm_hash_dynamic_clients_freq(verbose=True)        
        
        # RQ2: How are NodeJS applications referencing WebAssembly? / How do developers instantiate WebAssembly modules?
        instantiation_type_bar_chart()
        table_offset_init(init_wasm_modules)

        # RQ3: How is host code interacting with WebAssembly code?
        avg_exports_per_wasm_file(interop_wasm_modules)
        calls_through_table(interop_wasm_modules)

        # RQ4: How much variance is there in how a WebAssembly Module is used by different clients?
        client_variance_in_export_calls(interop_wasm_modules)


    if METADCE: 
        (init_wasm_modules, interop_wasm_modules) = init_no_interop(verbose=True)
        run_debloat_experiment(interop_wasm_modules)
        debloat_graph()

    if EVOLUTION: 
        wasm_evolution()
