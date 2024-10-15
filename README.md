# NodeWasmDataset (NoWaSet): A Dataset of executable Node.js packages that use WebAssembly

This is a dataset of 510 executable Node.js packages that exercise 217 unique WebAssembly modules. This dataset can be used to test WebAssembly performance, interoperation with JavaScript, etc. 

## Overview 

The repository is organized as follows: 
- `data`: 
    - `collect-dataset`: Metadata for dataset collection. 
    - `dumped-wasm-files`: Dumps of WebAssembly modules executed during package test execution. 
    - `dynamic-results`: Dynamic logs of packages in the dataset. 
    - `graphs`: Graphs in the paper. 
    - `summary-json`: Intermediate JSON files used to build graphs. 
    - `dependency-analysis-results.json`: Dependency analysis results for packages in the dataset. 
    - `node-wasm-set.json`: Data for each package in the dataset including package metadata, commit SHA, how to build, install and run package tests.  
- `dataset`: A DockerImage of the dataset without any analyses.   
- `scripts`
    - Python scripts to collect the dataset, perform a dependency analysis and collect dynamic logs over the dataset. 
    - Versions of node with different flags, used in dataset collection and the dynamic analysis. 
    - The tracing code injected into JavaScript files for the dynamic analysis.

## Running the analyses

Run the Docker container in the top-level directory using the `run-docker.sh` script. 
You can then run various scripts as follows: 
- `python3 collect-dataset.py`: Script for dataset collection
- `python3 dependency-analysis.py`: Script to run the static analysis and dependency analysis 
- `python3 collect-dynamic-results.py --output-dir <DIR>`: Script to collect dynamic logs for each package in the dataset. This runs in parallel and takes quite a bit of RAM. You can pass in any directory after the `--output-dir` flag. `./../data` is usually passed in.  
- `python3 collect-dynamic-results.py --output-dir <DIR> --single-repo <PACKAGE_NAME>`: Script to collect dynamic logs for a single package that is passed in. 
- `python3 get-summary-data.py`: Script to get JSON files in `data/summary-json`. These JSON files are used to generate graphs. They operate over dynamic logs in `data/dynamic-results` that have been compressed for GitHub. Make sure to decompress these files before running this script. 
- `python3 get-graphs.py --dependency`: Get results over static data of packages in the dataset. 
- `python3 get-graphs.py --dynamic`: Get results over dynamic logs of packages in the dataset.
- `python3 get-graphs.py --metadce`: Get results for DCE experiment.