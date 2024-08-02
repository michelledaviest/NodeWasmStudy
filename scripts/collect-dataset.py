import re
import json
import csv
import os
import glob 

# For scraping NPM for packages 
import requests
from bs4 import BeautifulSoup   
from time import sleep
from collections import Counter

from utils import run, install_and_build_repo, rm_rf_repo, clone_repo_at_sha
from utils import TESTING_REPO, REALWASM_JSON
from utils import NUM_TOP_PACKAGES_TO_ANALYZE, ANALYZED_REPOS_JSON, ANALYZED_NPM_PACKAGES_JSON, NPM_PACKAGES_SORTED_DOWNLOADS


NPM_FILTER = "./../tools/npm-filter/src/diagnose_github_repo.py"
NPM_FILTER_OUTPUT_DIR = "./../data/collect-dataset/npm_filter_results"

GHTOPDEP_OUTPUT_DIR = "./../data/collect-dataset/ghtopdep_results"

# Note:
# Use process pool - multi process pool executor 
# - multiprocessing.lock uses shared mem 
# Pool map: call function over an array of args 
# - multiprocessing.pool.map
# - you have control over the pool 

# Get metadata using registry.npmjs.org
def get_npm_metadata(name):
    # https://registry.npmjs.org/source-map
    metadata_url = "https://registry.npmjs.org/{}".format(name)
    response = requests.get(metadata_url)
    meta = response.json()
    if "versions" in meta.keys():
        del meta["versions"]
    return meta

def get_github_repo_metadata(repo_url): 
    metadata_url = "https://api.github.com/repos/{}".format(repo_url.replace("https://github.com/", ""))
    response = requests.get(metadata_url)
    return response.json()

def clone_repo(repo_url, repo_dir): 
    if os.path.isdir(repo_dir): 
        return True 
    clone_results = run(['git', 'clone', '--depth', '1', repo_url], cwd=TESTING_REPO, check=False)
    return clone_results.returncode == 0

def get_repo_SHA(repo_dir):
    repo_sha = run(['git', 'rev-parse', 'origin'], cwd=repo_dir)
    return repo_sha.stdout if repo_sha.returncode == 0 else None 

# scrape-npm (Scrape npm and find wasm libraries with their metadata)
def scrape_npm_for_packages_with_keyword_wasm():
    
    print("Scraping npmjs.com for packages with WebAssembly")

    URL_TEMPLATE = "https://www.npmjs.com/search?ranking=popularity&q=keywords%3Awasm%2CWebAssembly&page={}&perPage=20"
    H3_RE = "<h3 .*>(.*)</h3>"

    with open(ANALYZED_NPM_PACKAGES_JSON, 'r') as scraped_npm_packages: 
        old_package_names = json.load(scraped_npm_packages)
    print("{} packages have already been scraped.".format(len(old_package_names)))
    
    new_package_names = {}
    pagenum = 0 

    while(1):

        URL = URL_TEMPLATE.format(pagenum)
        page = requests.get(URL)

        if page.status_code == 200: 

            print("Scraping results page number: {}".format(pagenum))
            soup = BeautifulSoup(page.content, "html.parser")

            packages_div = soup.find("div", {"class": "d0963384 ph3 pl4-l pr0-l w-90-l pt2-ns"})
            package_sections = packages_div.find_all("section", {"class": "ef4d7c63 flex-l pl1-ns pt3 pb2 ph1 bb b--black-10"})
            
            # exceeding the number of pages with matches just gives you empty pages so break out of loop  
            if len(package_sections) == 0: 
                
                if len(new_package_names) == 0: 
                    print("No new packages have been found.")
                else: 

                    print("{} new packages found!".format(len(new_package_names)))
                    print("Package names can be found in ./../metadata/scraped_npm_wasm_packages.json")

                    with open(ANALYZED_NPM_PACKAGES_JSON, 'w', encoding='utf-8') as scraped_npm_packages:
                        json.dump({**old_package_names, **new_package_names}, scraped_npm_packages, ensure_ascii=False, indent=2)

                break 

            # extract library names     
            for package_section in package_sections:
                h3_element = str(package_section.find("h3"))
                name = re.match(H3_RE, h3_element).groups()[0]
                if name not in old_package_names.keys(): 
                    
                    # Get metadata                    
                    metadata = get_npm_metadata(name)
                    new_package_names[name] = { "metadata": metadata }

                    # Save intermediate results in case of crash
                    # if the number of package_names is a multiple of 100, update json with npm_wasm_packages names 
                    if len(new_package_names.keys()) > 0 and len(new_package_names.keys()) % 100 == 0: 
                        print("{} new packages found...".format(len(new_package_names)))
                        with open(ANALYZED_NPM_PACKAGES_JSON, 'w', encoding='utf-8') as scraped_npm_packages:
                            json.dump({**old_package_names, **new_package_names}, scraped_npm_packages, ensure_ascii=False, indent=2)

            pagenum += 1 

        else: 

            print("You're being rate limited by npmjs.com, let's wait for 120 seconds") 
            sleep(120)

    with open(ANALYZED_NPM_PACKAGES_JSON, 'r') as scraped_npm_packages: 
        return json.load(scraped_npm_packages)    

def get_k_top_downloaded_packages(k): 
    npm_packages = [] 
    with open(NPM_PACKAGES_SORTED_DOWNLOADS, mode ='r') as file:
        csvFile = csv.reader(file)
        for lines in csvFile:
            if len(npm_packages) == k: 
                return npm_packages
            package, download_count = lines
            npm_packages.append(package)
    return npm_packages

def check_if_repo_has_wasm(repo_dir):
    # Grep for "WebAssembly" all .js files in the repo and return true if it does exist 
    for file in glob.glob(repo_dir + '/**', recursive=True):
        if file.endswith(".wasm"):
            return True
        elif file.endswith(".wasm.js"):
            return True 
        elif file.endswith(".js") or file.endswith(".ts") or file.endswith(".cjs") or file.endswith(".mjs"): 
            with open(file, 'r') as f: 
                for line in f.readlines(): 
                    if "WebAssembly" in line: 
                        return True
    return False 

def check_if_tests_exercise_wasm(repo_dir, npm_filter_results): 
    
    tests_exercise_wasm = False 

    # add current directory into PATH since we have script node that points to a version of node that does not have WebAssembly enabled 
    my_env = os.environ.copy()
    node_noexpose_wasm_path = f"{os.getcwd()}/node-no-expose-wasm"
    my_env["PATH"] = f"{node_noexpose_wasm_path}:{my_env['PATH']}"    

    # Run all tests that were previously passing and append 'executes_wasm' to it if they fail
    for test_script in npm_filter_results["testing"]:
        if "ERROR" in npm_filter_results["testing"] and npm_filter_results["testing"]["ERROR"]: 
            # This test had previously failed so we disregard it  
           continue
        
        test_result = run(["npm", "run", test_script], check=False, cwd=repo_dir, env=my_env)        
        # The test should fail which means that the returncode should be non-zero 
        test_exercises_wasm = True if test_result.returncode != 0 else False
        if test_exercises_wasm: 
            return True 
        else: 
            continue

    return tests_exercise_wasm

# scrape-dependents (Scrape top 30 dependents from GitHub with min 5 stars using ghtopdep) 
def scrape_dependents_ghtopdep(repo_url, repo_full_name):     
    results_json = f"{GHTOPDEP_OUTPUT_DIR}/{'__'.join(repo_url.split('/')[-2:])}__results.json"
    dependents_json = []

    if os.path.exists(results_json): 
        dependents_json = json.load(open(results_json,"r"))
    else: 
        try: 
            ghtopdep_results = run(["ghtopdep", repo_url, "--minstar=5", "--rows=30", "--json"], check=False, timeout=10*60)
            if ghtopdep_results.returncode == 0: 
                dependents_json = re.compile(r"(\[.*\])").search(ghtopdep_results.stdout).groups()[0]
                dependents_json = json.loads(dependents_json)
            else: 
                print("ERROR when getting dependents.")
        
        except TimeoutError: 
            print("TimeoutError when getting dependents (10min timeout).")            

    with open(results_json, 'w+') as f:
        json.dump(dependents_json, f, ensure_ascii=False, indent=2)
    
    return dependents_json

def npm_filter_results_summarize(result):
    # The npm filter results can have a key "setup", which describes what happened while setting up the repo
    # You can have pkg_json_ERROR, which means that there was no package.json to be found; 
    # repo_cloning_ERROR, which means that there was an error while cloning the repo 
    # repo_commit_checkout_ERROR, which means that there was an error while cloning a specific commit 
    #   -> not aplicable to us since we do not specify which commit to clone  
    not_js_project = "setup" in result.keys() and "pkg_json_ERROR" in result["setup"].keys()                 
    
    # npm filter ERROR indicates runtime error (rt) 
    # You can have an ERROR show up in installation, building and testing
    install_rt_error = "installation" in result.keys() and "ERROR" in result["installation"].keys()              
    build_rt_error = "build" in result.keys() and "ERROR" in result["build"].keys()              
    tests_success = False
    num_passing_tests, num_failing_tests = 0, 0
    if "testing" in result:
        for test in result["testing"]:
            test = result["testing"][test]
            # There has to exist atleast one test script that ran
            # NOTE: We are disregarding repos that have test suites that partially pass
            # If we still don't get enough repos we can re-run while allowing repos with partially passing test cases. 
            tests_success = tests_success or "ERROR" not in test.keys() 
            # npm filter num_failing_tests indicates that the tests ran and failed
            if "num_passing" in test.keys(): 
                num_passing_tests += test["num_passing"]
            if "num_failing" in test.keys(): 
                num_failing_tests += test["num_failing"]
    
    summary = {
        "js_project": not not_js_project,
        "install_success": not install_rt_error, 
        "build_success": not build_rt_error, 
        "test_success": tests_success, 
        "total_num_passing_tests": num_passing_tests, 
        "total_num_failing_tests": num_failing_tests
    }

    return summary

def run_npm_filter(repo_dir, repo_name, repo_full_name_path_safe): 
    npm_filter_json_file = f"{NPM_FILTER_OUTPUT_DIR}/{repo_name}__results.json"
    expected_json_file = f"{NPM_FILTER_OUTPUT_DIR}/{repo_full_name_path_safe}__results.json"

    # Check if the repo has already been npm_filter analyzed
    if os.path.exists(expected_json_file):
        with open(expected_json_file, 'r') as npm_filter_res: 
            return json.load(npm_filter_res)

    try:
        npm_filter_result = run(
            ["python3", NPM_FILTER, "--repo_local_dir", repo_dir, "--output_dir", NPM_FILTER_OUTPUT_DIR], 
            timeout=5*60
        )
        if npm_filter_result.returncode != 0: 
            return None 
        run(['mv', npm_filter_json_file, expected_json_file])
        with open(expected_json_file, 'r') as npm_filter_res: 
            return json.load(npm_filter_res)
         
    except TimeoutError: 
        return None

def run_analysis_over_repo_url(repo_url, repo_json=None):
    #print("Analyzing", repo_url)

    repos_to_skip = ["fanout/fanout-graphql-tools", "fanout/express-eventstream"]
    if True in [repo_name in repo_url for repo_name in repos_to_skip]: 
        return (False, "Killed")

    repo_name = repo_url.split("/")[-1]
    repo_full_name = "/".join(repo_url.split("/")[-2:])
    repo_full_name_path_safe = "__".join(repo_full_name.split("/"))
    if repo_json is None: 
        repo_dir = f"{TESTING_REPO}/{repo_name}"
    else: 
        repo_dir = f"{TESTING_REPO}/{repo_full_name_path_safe}"

    try: 
        # Clone repo 
        if repo_json is not None: 
            clone_repo_at_sha(
                path_safe_repo_full_name=repo_full_name_path_safe,
                ssh = repo_json["repo_metadata"]["clone_url"],
                commit_sha= repo_json["repo_metadata"]["commit_SHA"],
                dir=TESTING_REPO
            )
        else: 
            clone_success = clone_repo(repo_url, repo_dir)
            if not clone_success:
                return (False, "Failed to clone")

        # Get npm filter results
        npm_filter_results = run_npm_filter(repo_dir, repo_name, repo_full_name_path_safe)
        if npm_filter_results is None:             
            rm_rf_repo(repo_dir)
            return (False, "npm_filter timeout")

        # Summarize the result 
        summary = npm_filter_results_summarize(result=npm_filter_results)

        if not summary["js_project"]: 
            rm_rf_repo(repo_dir)
            return (False, "Not a JS project (via NPM filter)")

        if not summary["install_success"] or not summary["build_success"]: 
            rm_rf_repo(repo_dir)
            return (False, "Install/Build fail (via NPM filter)")

        if not summary["test_success"]: 
            rm_rf_repo(repo_dir)
            return (False, "No successful test scripts (via NPM filter)")
        
        install_build_success = install_and_build_repo(repo_name, npm_filter_results, repo_dir) 
        if not install_build_success: 
            rm_rf_repo(repo_dir)
            return (False, "Install/Build fail on local.")

        # Check that the repo has atleast one .wasm file OR .wasm.js file OR "WebAssembly" in any .js/.ts file 
        repo_has_wasm = check_if_repo_has_wasm(repo_dir)
        if not repo_has_wasm: 
            rm_rf_repo(repo_dir)
            return (False, "No WebAssembly in repo")

        # Check if the repos tests exercise .wasm files 
        tests_exercises_wasm = check_if_tests_exercise_wasm(repo_dir, npm_filter_results)
        if not tests_exercises_wasm:
            rm_rf_repo(repo_dir)
            return (False, "Does not exercise Wasm through tests")

        if repo_json is None: 
            repo_sha = get_repo_SHA(repo_dir)
            repo_metadata = get_github_repo_metadata(repo_url)
            repo_metadata["commit_SHA"] = repo_sha
            rm_rf_repo(repo_dir)
            return (True, {
                "repo_metadata": repo_metadata,
                "npm_filter": npm_filter_results,
            })
        else: 
            rm_rf_repo(repo_dir)
            return (True, repo_json)           
        
    except Exception as e: 
        return (False, f"Exception {repr(e)} occured.")    

def diagnose_repo(repo_url, realwasm, analyzed_repos, repo_json=None, get_dependents=False):
    repo_full_name = "/".join(repo_url.split("/")[-2:])
    success, repo_obj = run_analysis_over_repo_url(repo_url=repo_url, repo_json=repo_json)
    dependents = []

    if success: 
        print(f"SUCCESS: {repo_full_name}")
        realwasm[repo_full_name] = repo_obj 

        if get_dependents:
            # Find repo dependents (top 30, min 5 stars) from github
            dependents = scrape_dependents_ghtopdep(repo_url, repo_full_name)
            dependents = [dependent['url'] for dependent in dependents]

        analyzed_repos[repo_full_name] = repo_obj
    else: 
        error_msg = repo_obj
        print(f"FAILURE: {repo_full_name}: {error_msg}")
        if repo_full_name in realwasm: 
            del realwasm[repo_full_name]
        analyzed_repos[repo_full_name] = {
            "FAILURE": error_msg
        }

    return dependents

def get_seed_npm_packages(num_top_downloaded, fresh=False): 
    if fresh:
        npm_packages = scrape_npm_for_packages_with_keyword_wasm()
    else: 
        with open(ANALYZED_NPM_PACKAGES_JSON, 'r') as scraped_npm_packages: 
            npm_packages = json.load(scraped_npm_packages)
   
    top_k_packages = get_k_top_downloaded_packages(num_top_downloaded)

    print(f"Adding top {num_top_downloaded} downloaded packages to scraped NPM packages")
    print(f"Current count of scraped NPM packages = {len(npm_packages)}")
    for count, package in enumerate(top_k_packages):
        if package not in npm_packages:
            print(f"Found a new package! {package}" )
            metadata = get_npm_metadata(name=package)
            npm_packages[package] = {
                "metadata": metadata
            }
            if len(npm_packages) % 100 == 0:
                print(f"Updating scraped NPM packages with 100 more packages. Len = {len(npm_packages)}, {num_top_downloaded-count} left.")
                with open(ANALYZED_NPM_PACKAGES_JSON, 'w') as scraped_npm_packages_f: 
                    json.dump(npm_packages, scraped_npm_packages_f, ensure_ascii=True, indent=2)

    return npm_packages    

def get_dataset(): 

    # Dataset file 
    with open(REALWASM_JSON, 'r') as analyzed_repos_f:
        realwasm = json.load(analyzed_repos_f)

    # Repos that have already been analyzed
    with open(ANALYZED_REPOS_JSON, 'r') as analyzed_repos_f:
        analyzed_repos = json.load(analyzed_repos_f)

    # Get initial set of NPM packages 
    npm_packages = get_seed_npm_packages(NUM_TOP_PACKAGES_TO_ANALYZE)

    worklist = []
    for package in npm_packages: 
        metadata = npm_packages[package]["metadata"]
        url = None
        if "links" in metadata:
            if "repository" in metadata["links"] and "github" in metadata["links"]["repository"]: 
                url = metadata["links"]["repository"]
                continue
        if "repository" in metadata: 
            if "url" in metadata["repository"] and "github" in metadata["repository"]["url"]: 
                regex = "^.*(?:https://)?github.com(?::)?/((?:\w|-|_|\.)*)/((?:\w|-|_|\.)*)(?:/tree(?:/.*)*|\.git(?:#master|#main|#ts|#experiment)|\"|$)"
                match = re.match(regex, metadata["repository"]["url"])
                if match is not None: 
                    repo_first_name, repo_last_name = match.groups(0)
                    #repo_last_name = match.groups(1)
                    if ".git" in repo_last_name: 
                        repo_last_name = repo_last_name.replace(".git", "")
                    url = f"https://github.com/{repo_first_name}/{repo_last_name}"
        if url is not None:
            worklist.append(url) 

    print(f"Intial worklist length: {len(worklist)}") 
    print(f"Repos analuzed so far: {len(analyzed_repos)}")
    try: 
        while len(worklist) > 0:

            if len(analyzed_repos) >= 5000:  
                break

            repo_url = worklist.pop()
            repo_full_name = "/".join(repo_url.split("/")[-2:])

            # If repo has already been analyzed, add dependents into worklist and continue 
            if repo_full_name in analyzed_repos: 
                
                if "ERROR" in analyzed_repos[repo_full_name]: 
                    continue

                # Make sure it is in realwasm
                if repo_full_name not in realwasm: 
                    worklist.append(repo_url)
                    del analyzed_repos[repo_full_name]
                
                # Add the dependents in just to make sure they've been analyzed too 
                dependents = scrape_dependents_ghtopdep(repo_url, repo_full_name)
                for dependent in dependents: 
                    worklist.append(dependent["url"]) 
                continue 

            dependents = diagnose_repo(repo_url, realwasm, analyzed_repos, get_dependents=True)
            worklist.extend(dependents)

            # Dump the dataset so far          
            with open(REALWASM_JSON, 'w') as analyzed_repos_f:
                json.dump(realwasm, analyzed_repos_f, ensure_ascii=False, indent=2)

        # Save repos that have been analyzed so far 
        with open(ANALYZED_REPOS_JSON, 'w') as analyzed_repos_f:
            json.dump(analyzed_repos, analyzed_repos_f, ensure_ascii=False, indent=2)

    finally: 

        print("No more repositories to analyze.")
        print(f"Dataset dumped in {REALWASM_JSON}.")
        # Dump the dataset so far          
        with open(REALWASM_JSON, 'w') as analyzed_repos_f:
            json.dump(realwasm, analyzed_repos_f, ensure_ascii=False, indent=2)

        print(f"Metadata on repositories that have been analyzed in {ANALYZED_REPOS_JSON}.")
        # Save repos that have been analyzed so far 
        with open(ANALYZED_REPOS_JSON, 'w') as analyzed_repos_f:
            json.dump(analyzed_repos, analyzed_repos_f, ensure_ascii=False, indent=2)

# Re-run the analysis over the current dataset 
# Should report successes on all repos 
def re_run_over_current_dataset(): 
    
    # Dataset file 
    with open(REALWASM_JSON, 'r') as realwasm_f:
        realwasm = json.load(realwasm_f)

    # Repos that have already been analyzed
    with open(ANALYZED_REPOS_JSON, 'r') as realwasm_f:
        analyzed_repos = json.load(realwasm_f)

    count = 0
    worklist = [repo for repo in realwasm]
    for repo in worklist: 

        count += 1
        print(f"{count}/{len(realwasm)}: ", end='')

        if repo == "babel/babel": 
            print("Skipping because it kills the script.")
            continue
        
        diagnose_repo(
            repo_url=realwasm[repo]["repo_metadata"]["html_url"], 
            realwasm=realwasm, 
            analyzed_repos=analyzed_repos, 
            repo_json= realwasm[repo]
        )
        
        # Save repos that have been analyzed so far
        with open(ANALYZED_REPOS_JSON, 'w+') as analyzed_f:
            json.dump(analyzed_repos, analyzed_f, ensure_ascii=False, indent=2)

        # Dump the dataset so far          
        with open(REALWASM_JSON, 'w') as realwasm_f:
            json.dump(realwasm, realwasm_f, ensure_ascii=False, indent=2)

    print("Finished re-running checks on entire dataset.")
    print(f"Updated dataset found at {REALWASM_JSON} with {len(realwasm)} repositories.")    

# Re-run the analysis over all previously analyzed repos  
# Add all newly successful repos to realwasm dataset 
# Once you re-run, re_analyzed_repo_file can be the new analyzed_repos.json 
def re_run_over_analyzed_repos(re_analyzed_repo_file): 
    # Repos that have already been analyzed
    with open(ANALYZED_REPOS_JSON, 'r') as analyzed_repos_f:
        analyzed_repos = json.load(analyzed_repos_f)

    # Repos that have already been analyzed
    with open(re_analyzed_repo_file, 'r') as analyzed_repos_f:
        already_re_analyzed_repos = json.load(analyzed_repos_f)

    # Dataset file 
    with open(REALWASM_JSON, 'r') as analyzed_repos_f:
        realwasm = json.load(analyzed_repos_f)
    
    re_analyzed_repos = already_re_analyzed_repos

    for repo_full_name in analyzed_repos: 
        repo_url = f"https://github.com/{repo_full_name}"
        if repo_full_name in re_analyzed_repos:
            continue 

        diagnose_repo(repo_url, realwasm, analyzed_repos)
        re_analyzed_repos.append(repo_full_name)        

        if len(re_analyzed_repos) % 10 == 0:

            # Save repos that have been analyzed so far 
            with open(re_analyzed_repo_file, 'w+') as re_analyzed_f:
                json.dump(re_analyzed_repos, re_analyzed_f, ensure_ascii=False, indent=2)

            # Dump the dataset so far          
            with open(REALWASM_JSON, 'w') as analyzed_repos_f:
                json.dump(realwasm, analyzed_repos_f, ensure_ascii=False, indent=2)

            # Save repos that have been analyzed so far 
            with open(ANALYZED_REPOS_JSON, 'w') as analyzed_repos_f:
                json.dump(analyzed_repos, analyzed_repos_f, ensure_ascii=False, indent=2)

# Make sure the dataset all points to unique github sources. 
# And match up their key names to the GitHub repo names to ensure consistency. 
def make_sure_unique(): 

    with open(REALWASM_JSON, 'r') as f: 
        realwasm = json.load(f) 

    with open(ANALYZED_REPOS_JSON, 'r') as f: 
        analyzed_repos = json.load(f)

    repo_name_to_url = {} 

    worklist = list(realwasm.keys())
    for count, repo_name in enumerate(worklist): 
        repo_url = realwasm[repo_name]["repo_metadata"]["html_url"]

        if repo_url in repo_name_to_url.values(): 
            print(f"{count}/{len(worklist)-1}: Duplicate found for {repo_name}. Removing.")
            del realwasm[repo_name]
            del analyzed_repos[repo_name]

            # Dump the dataset so far          
            with open(REALWASM_JSON, 'w') as analyzed_repos_f:
                json.dump(realwasm, analyzed_repos_f, ensure_ascii=False, indent=2)

            # Save repos that have been analyzed so far 
            with open(ANALYZED_REPOS_JSON, 'w') as analyzed_repos_f:
                json.dump(analyzed_repos, analyzed_repos_f, ensure_ascii=False, indent=2)

        else: 
            repo_full_name = "/".join(repo_url.split("/")[-2:])
            repo_name_to_url[repo_full_name] = repo_url 
            if repo_full_name != repo_name: 
                print(f"{count}/{len(worklist)-1}: Wrong repo name found for {repo_name}, changing.")
                realwasm_val = realwasm[repo_name]
                analyzed_repos_val = analyzed_repos[repo_name]
                del realwasm[repo_name]
                del analyzed_repos[repo_name]
                realwasm[repo_full_name] = realwasm_val
                analyzed_repos[repo_full_name] = analyzed_repos_val

                # Dump the dataset so far          
                with open(REALWASM_JSON, 'w') as analyzed_repos_f:
                    json.dump(realwasm, analyzed_repos_f, ensure_ascii=False, indent=2)

                # Save repos that have been analyzed so far 
                with open(ANALYZED_REPOS_JSON, 'w') as analyzed_repos_f:
                    json.dump(analyzed_repos, analyzed_repos_f, ensure_ascii=False, indent=2)



run(['rm', '-rf', TESTING_REPO], check=False)
run(['mkdir', '-p', TESTING_REPO])

get_dataset()
print() 

make_sure_unique()

