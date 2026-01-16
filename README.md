# NodeWasmDataset (NoWaSet): A Dataset of executable Node.js packages that use WebAssembly

This is a dataset of 510 executable Node.js packages that exercise 217 unique WebAssembly modules. This dataset can be used to test WebAssembly performance, interoperation with JavaScript, etc. This repository is also an artifact for the ICSE 2026 paper _An Empirical Study of WebAssembly Usage in Node.js_. The paper can be found in the repository.

## Running via Docker

To build and run the artifact, simply run `chmod +x run-docker.sh && ./run-docker.sh`. The image itself is about 3.8GB on disk and takes between 5 and 15 minutes to build, depending on hardware and network connection.

## Container Organization

The repository is organized as follows: 
- `data`: 
    - `collect-dataset`: Metadata for dataset collection. 
    - `debloat-binaries`: Wasm binaries debloated with `wasm-metadce`.
    - `dumped-wasm-files`: Dumps of WebAssembly modules executed during package test execution. 
    - `dynamic-results`: Dynamic logs of packages in the dataset. 
    - `graphs`: Graphs in the paper. 
    - `summary-json`: Intermediate JSON files used to build the graphs and results. 
    - `dependency-analysis-results.json`: Dependency analysis results for packages in the dataset. 
    - `node-wasm-set.json`: Data for each package in the dataset including package metadata, commit SHA, how to build, install and run package tests.
    - `wasm-evolution.json`: Study of the evolution of Wasm binary files in 50 packages.    
- `dataset`: A DockerImage of the dataset without any analyses.   
- `scripts`:
    - Python scripts to collect the dataset, perform a dependency analysis and collect dynamic logs over the dataset. 
    - Versions of node with different flags, used in dataset collection and the dynamic analysis. 
    - The tracing code injected into JavaScript files for the dynamic analysis.

## Evaluation pipeline
The evaluation in the paper runs a static and dynamic analysis over 510 packages to study the interoperation between WebAssembly and JavaScript. The static analysis is run over every JavaScript and TypeScript file in an NPM package to find Wasm modules and determine their distribution methods. The dynamic analysis instruments the source code of an NPM package and runs its tests to collect logs of WebAssembly-JavaScript interopertion. This instrumentation-logging cycle is also run over every library that a package depends upon that contains WebAssembly. The logs for each library are saved under a JSON file named after the library. For more details on the analyses, please refer to the paper. Both these analyses are expensive and have been run on a 128 core machine with 125GB RAM, with 510 packages being analyzed in parallel. Once static results and dynamic logs are collected for each package, the graphs and results of the paper are extracted from these logs as shown in the illustration below. First, we explain how to obtain the graphs and numerical results in the paper. Then we describe how to extract logs for a given package. 

``` 
  Dataset
               +-------------+
 package1 ---->|             |      Static Analysis results and Dependency Analysis results
 package2 ---->| dependency- |----> data/dependency-analysis-results.json
    ...        | analysis.py |                
 packageN ---->|             |
               +-------------+
                                    Dynamic Logs in data/dynamic-results
               +-------------+
 package1 ---->| collect-    |----> self.json, long.json
 package2 ---->| dynamic-    |----> self.json, vite.json, next.json, source-map.json
    ...        | results.py  |                ....
 packageN ---->|             |----> self.json, long.json, hash-wasm.json
               +-------------+     |_________________________________________________|
                                           ↓
                                    +---------------------+
                                    | get-summary-data.py |
                                    +---------------------+
                                           ↓  
                                      JSON files in data/summary-json
                                           ↓                                            
                                    +---------------------+
                                    | get-graphs.py       |
                                    |   --dependency /    |
                                    |   --dynamic /       |
                                    |   --metadce /       | 
                                    |   --evolution       |
                                    +---------------------+
                                           |
                                           |----> Graphs 
                                           |----> Numerical results (Averages, etc)                 
```

## Reproducing Graphs and Results  
Run `cd /home/RealWasm/scripts` before running the commands listed below. The graphs produced by these commands are dumped in `data/graphs` for inspection. Each script also produces every numerical result in the paper, often in the same/similar sentence as reported in the paper. These together should replicate all the claims and findings in the paper.

### Dependency Analysis 
Running `python3 get-graphs.py --dependency` in the docker container will dump the results over static data of packages in the dataset. These results are explained in Section 4.1 _How do Node.js packages depend on WebAssembly?_ and 4.4.1: _Different Methods of Distributing WebAssembly_. The static analysis results include an additional 54 packages (explained on Page 4, paragraph 1), which is why running this script reports that the total number of packages in dataset are 564.

### Evolution of WebAssembly in NPM Packages
Running `python3 get-graphs.py --evolution` dumps the results of the study tracking the evolution of Wasm in NPM packages, as discussed in Section 4.2 _How has WebAssembly usage in NPM packages evolved over time?_

### Dynamic Results  
Running `python3 get-graphs.py --dynamic` will dump results over the dynamic logs of packages in the dataset. The results are discussed in Section 4.3 _How comprehensively do packages in the dataset test the WebAssembly modules they depend upon?_, 4.4 _How are JavaScript program analysis and engine developers affected by the presence of WebAssembly?_ and 4.5 _What optimization opportunities exist for packages that use WebAssembly?_. For the ease of the user, each result is reported with the appropriate subheading topic labeled as 'QUERY', such as:  
- What percentage of WebAssembly modules are instantiated via streaming, buffer and synchronously?
- What values are the offsets into a WebAssembly function table initialized with?
- Do WebAssembly Modules export the same functions in a table and explicitly?

### Binary Debloating 
`python3 get-graphs.py --metadce` runs `wasm-metadce` over each dumped Wasm binary and client pair, discussed in Section 4.5.2 _Exported Functions Called by JavaScript_. This script takes 10 minutes to run. 

## Running the analyses 
We illustrate the running of the static and dynamic analyses over a single package [hexojs/hexo-generator-feed](https://github.com/hexojs/hexo-generator-feed). This package is the first package in the dataset and the metadata for it can be inspected under the "hexojs/hexo-generator-feed" key in `data/node-wasm-set.json`. The graphs and results of the paper should not change if logs are recollected over any of the packages. 

### Static and Dependency Analysis
Running `python3 dependency-analysis.py --static --dependency --single-repo <PACKAGE_KEY>` will run the static analysis and dependency analysis for a given package after cloning its source code and installing and building the package. The results are dumped on stdout. The static analysis runs over every JavaScript and Typescript file in the source code of the package and the source code of each of its dependencies. It reports on the files that contain WebAssembly modules as well as their distribution methods. The dependency analysis extracts a dependency tree between the package and all its dependencies that contain WebAssemby. The latter is used during dynamic analysis to determine the dependencies to instrument and collect dynamic logs over.   

Run the following command to ensure that the static analysis works as expected: `python3 dependency-analysis.py --static --dependency --single-repo hexojs/hexo-generator-feed`. You should see the following on the terminal after 3 minutes. It lists that a WebAssembly Module was found in the `camaro.wasm` file. Note that WebAssembly Modules can also be embedded in JavaScript files as arrays or base64 strings. The script also reports on the distribution methods of the files that contain WebAssembly. We see here that the found module is in a binary file. A unique hash is generated for each Wasm module which is mapped to its distribution method. This is omitted for brevity but can be printed out easily. The stdout also lists camaro as a dependent library that contains WebAssembly, for which dynamic logs are collected during the dynamic analysis.

```
Static Analysis for hexojs/hexo-generator-feed:
Files with Wasm Modules:
  ./TESTING_REPO/hexojs__hexo-generator-feed/node_modules/camaro/dist/camaro.wasm
Unique Wasm Counts:
{'array': 0, 'base64': 0, 'binary': 1}
Dependency Tree for hexojs/hexo-generator-feed:
{
  "camaro": []
}
```

### Dynamic Analysis 
Running `python3 collect-dynamic-results.py --output-dir <DIR> --single-repo <PACKAGE_KEY>` will collect dynamic logs for a single package that is passed in, in a output directory that is also passed in. Run the following commands to ensure that the dynamic analysis works as expected: 

```
mkdir TMP 
python3 collect-dynamic-results.py --output-dir TMP --single-repo hexojs/hexo-generator-feed
```
After a minute, you should see the message: `SUCCESS: hexojs/hexo-generator-feed results dumped in TEMP repo.`
Inspecting the `TMP` directory should reveal a `dumped-wasm-files` directory which contains the Wasm module that hexo-generator-feed's tests have instatiated. You should also find a `dynamic-analysis` directory that contains `self.json` and `camaro.json`. The former are dynamic logs over the instrumented source code of the hexo-generator-feed and the latter contains dynamic logs over the instrumented source code of a dependency of hexo-generator-feed, camaro, which was determined to contain WebAssembly by the static analysis.  

## Extending the Artifact (Reusability)
This artifact contains NoWaSet, the first dynamically executable dataset of 510 NPM packages that interoperate with WebAssembly. This dataset can be used to test static and dynamic analyses against and develop tools for the JavaScript-WebAssembly ecosystem. We have made every analysis used in the paper available in this artifact which further improves its reusability. In fact, any researchers or developers looking to prototype a static or dynamic analysis over NPM packages containing WebAssembly may benefit from this artifact. For example, the `collect-dataset.py` script can be used to collect a more extensive dataset in the future. The static and dynamic analysis provide a template for other analyses over JavaScript and WebAssembly. Additionally, these scripts are all retrofitted with the `--single-repo` flag that allows collection of analysis results over a single NPM package. Since the paper recommends various pragmatic assumptions for analysis developers and engine writers, a user can run our analyses over their package to determine if the use WebAssembly in a way that allows for these assumptions. This can be useful when writing cross-language optimizations such as specializing a WebAssembly binary to a particular JavaScript client.