import subprocess
import shlex
import textwrap
import os 
import hashlib
import re

import matplotlib.pyplot as plt
#plt.rc('text', usetex=True)
#plt.rc('text.latex', preamble=r'\usepackage{libertine}')
plt.rc('font', family='serif')
plt.rc('font', size=30)

REALWASM_JSON = "./../data/node-wasm-set.json"
DEP_ANLYSIS_JSON = "./../data/dependency-analysis-results.json"
TESTING_REPO = "./TESTING_REPO"

NUM_TOP_PACKAGES_TO_ANALYZE = 100 
ANALYZED_REPOS_JSON = "./../data/collect-dataset/analyzed_repos.json"
ANALYZED_NPM_PACKAGES_JSON = "./../data/collect-dataset/scraped_npm_packages.json"
NPM_PACKAGES_SORTED_DOWNLOADS = "../data/collect-dataset/all_npm_packages_sorted_download_counts.csv"

DYNAMIC_RESULTS = "./../data/dynamic-results"
DUMPED_WASM_FILES = "./../data/dumped-wasm-files"

SUMMARY_JSON_DIR = "./../data/summary-json"
INSTANTIATION_JSON = f"{SUMMARY_JSON_DIR}/instantiation-counts.json"
WASM_STATIC_INFO_JSON = f"{SUMMARY_JSON_DIR}/wasm-static-info.json"
EXPORTS_CALLED_COUNT_JSON = f"{SUMMARY_JSON_DIR}/exports-called-count.json"
CALLS_THROUGH_TABLE_JSON = f"{SUMMARY_JSON_DIR}/calls-through-table.json"
WASM_IMPORTS_JSON = f"{SUMMARY_JSON_DIR}/wasm-imports.json"
WASM_MODULES_INTEROP_TYPE = f"{SUMMARY_JSON_DIR}/wasm-modules-interop-type.json"
INTEROP_BUT_NEVER_INSTANTIATE = f"{SUMMARY_JSON_DIR}/interop-no-init.json"

IGNORED_REPOS = [
    # Timeout errors (21) 
    'epicweb-dev/kcdshop', 'ChainSafe/js-libp2p-gossipsub', 'Shopify/ui-extensions', 'koel/koel', 'Namchee/windgraph', 
    'pybricks/pybricks-code', 'reearth/quickjs-emscripten-sync', 'partykit/partykit', 'cloudflare/next-on-pages', 
    'FiniteLooper/LyricConverter', 'mattdesl/qoa-format', 'FabricLabs/fabric', 'lucky-chap/kaminari', 'actualbudget/actual', 
    'yeemachine/kalidokit', 'ArnaudBuchholz/training-ui5con18-opa', 'astefanutti/decktape', 'c-frame/aframe-super-hands-component', 
    'facebook/create-react-app', 'ashleyrudland/nextjs_vps', 'react-declarative/cra-template-react-declarative'

    # Linter errors (31)
    "ref-finance/ref-ui", "theopensource-company/playrbase", "liuw5367/chatgpt-web", "VenusProtocol/venus-protocol-interface", 
    "cryptoloutre/solana-tools", "stripe/stripe-node", "coderaiser/putout", "stegripe/bajigur",     
    "ilyhalight/voice-over-translation", "istanbuljs/babel-plugin-istanbul", "ets-berkeley-edu/boac", "rapid7/awsaml", 
    "PxlSyl/tailwind-nextjs-starter-blog-i18n", "PrabhuKiran8790/prabhukirankonda", "import-js/eslint-plugin-import", 
    "AykutSarac/jsoncrack.com", "juunini/gltf-optimizer", "iter-tools/iter-tools", "Esri/solutions-components", "dlarroder/dalelarroder", 
    "STARK-404/Whatsapp-spy", "WhiskeySockets/Baileys", "paritytech/pwasm-runtime-js", "frictionlessdata/datapackage", "cerc-io/watcher-ts", 
    "vuejs/jsx-vue2", "jake-pauls/snowpack-template-ts-rust-wasm", "onwidget/astrowind", 

    # Runtime Exceptions
    "smapiot/pidoc", 
    "bluesky-social/react-native-uitextview", 
    "shoelace-style/shoelace", 
    "traPtitech/traQ_S-UI", 
    "babel/babel", 
]

def run(
    cmd,
    verbose=False,
    cwd=None,
    check=True,
    capture_output=True,
    encoding="utf-8",
    # Specify an integer number of seconds
    timeout=-1,
    **kwargs
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

def get_realwasm_log(io_result): 
    realwasm_log = []
    std_err = []    
    REALWASM_LOG_REGEX = "^ *RealWasmLog"
    realwasmline = re.compile(REALWASM_LOG_REGEX)

    for line in io_result.stdout.split('\n'):
        if realwasmline.match(line) is not None:
            realwasm_log.append(line)

    for line in io_result.stderr.split('\n'):
        if realwasmline.match(line) is not None:
            realwasm_log.append(line)
        else: 
            std_err.append(line)

    return (realwasm_log, std_err)

def install_and_build_repo(repo_name, npm_filter_results, repo_dir): 

    # Run the install and build scripts, if they exist 
    install_possible = "installation" in npm_filter_results.keys() and "ERROR" not in npm_filter_results["installation"].keys()
    if install_possible: 

        install_script = npm_filter_results["installation"]["installer_command"]

        install_result = run(shlex.split(install_script), check=False, cwd=repo_dir, env=get_env_with_node_with_flags())        
        if install_result.returncode != 0: 
            install_result = run(shlex.split(install_script) + ['--force'], check=False, cwd=repo_dir, env=get_env_with_node_with_flags())        

        # Browserslist: caniuse-lite is outdated. Please run: npx update-browserslist-db@latest
        # if repo_name in ["video-dev/hls.js", "Quramy/pico-ml", "collab-project/videojs-record", "jelster/space-truckers", "ueberdosis/tiptap"]: 
        #     run(["npx", "--yes", "update-browserslist-db@latest"], check=False, cwd=repo_dir)

        if repo_name == 'yisibl/resvg-js': 
            run(['npm', 'i', 'benny'], check=False, cwd=repo_dir, env=get_env_with_node_with_flags())

        if repo_name == 'jake-pauls/snowpack-template-ts-rust-wasm': 
            run(['npm', 'i', 'crypto'], check=False, cwd=repo_dir, env=get_env_with_node_with_flags())
                
        if install_result.returncode != 0:
            with open("install-stdout", "a+") as f:
                f.write(f"INSTALL ERROR ------------------------------------------------------------- {repo_name}:\n")
                f.write(install_result.stdout)
                f.write("\n\n")
            with open("install-stderr", "a+") as f:
                f.write(f"INSTALL ERROR ------------------------------------------------------------- {repo_name}:\n")
                f.write(install_result.stderr)
                f.write("\n\n")
            return (False, None)
        else: 
            realwasmlog, _ = get_realwasm_log(install_result)

    build_possible = "build" in npm_filter_results.keys() and "ERROR" not in npm_filter_results["build"].keys()              
    if build_possible:
        build_scripts = npm_filter_results["build"]["build_script_list"]
        for build_script in build_scripts:
            if "lint" in build_script: continue
            build_result = run(
                            shlex.split("npm run "+ build_script), 
                            check=False,
                            cwd=repo_dir, 
                            env=get_env_with_node_with_flags()
                        )
            if build_result.returncode != 0:
                with open("build-stdout", "a+") as f:
                    f.write(f"BUILD ERROR ------------------------------------------------------------- {repo_name}:\n")
                    f.write(build_result.stdout)
                    f.write("\n\n")
                with open("build-stderr", "a+") as f:
                    f.write(f"BUILD ERROR ------------------------------------------------------------- {repo_name}:\n")
                    f.write(build_result.stderr)
                    f.write("\n\n")
                return (False, None) 
            else: 
                build_realwasmlog, _ = get_realwasm_log(build_result)
                realwasmlog.extend(build_realwasmlog)

    return (True, realwasmlog)  

def rm_rf_repo(repo_dir): 
    run(['rm', '-rf', repo_dir])

def checkout(branch_name, commit_sha, repo_dir): 
    run(["rm", "-rf", ".git/hooks"], cwd=repo_dir, check=False) 
    result = run(['git', 'checkout', '-b', branch_name, commit_sha.strip()], cwd=repo_dir)
    if result.returncode != 0: 
        print("git checkout did not succeed")
        print(result.stderr)
        print(result.stdout)
        import sys 
        sys.exit()

def get_static_info(wasm_hash_file): 
    import json 
    GET_WASM_STATIC_INFO = "./get-wasm-static-info/target/release/get-wasm-static-info"
    static_info = run([GET_WASM_STATIC_INFO, "--binary", wasm_hash_file]) 
    return json.loads(static_info.stdout)


def hash_wasm_file(file_path):
    with open(file_path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()

def hash_wasm_js_file(file_path):
    js_code = f"console.log(require('crypto').createHash('sha256').update(Buffer.from(require({file_path!r}), 'base64')).digest('hex'));"
    result = run(["node", "-e", js_code], check=True, capture_output=True)
    return result.stdout.rstrip()

def find_wasm_files_in_dir(dir):
    wasm_files = []
    for root, _dirs, files in os.walk(dir):
        for file in files:
            path_to_file = os.path.join(root, file)
            if file.endswith(".wasm"):
                wasm_files.append(path_to_file)
            elif file.endswith(".wasm.js"):
                wasm_files.append(path_to_file)
    return wasm_files 