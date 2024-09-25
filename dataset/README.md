# NoWaSet (NodeWasmDataset) 

This is a dataset of 510 executable Node.js packages that exercise 217 unique WebAssembly modules. The dataset can be found in the `node-wasm-set.json` file. It is organized as follows: 
```
{
    "org/user-name/github-repo-name": {     // Github Source Repository of the Node.js package
        "github_metadata": {                // Metadata of the GitHub source repository
            ...
            "html_url": ... ,               // URL to GitHub repo
            "commit_SHA": ... ,             // Commit SHA used in experiments and metadata
            ... 
        }, 
        "source_languages": { ... },        // Source Languages of the GitHub repo
        "scripts" : {
            "install": ... ,                // Script used to install the Node.js package.
            "build"  : ... ,                // Script(s) used to build the Node.js package 
            "tests"  : {
                "test_name" : {             // Test name 
                    "script": ... ,         // Script to run the test
                    ...                     // Other metadata related to running the test (number of passing tests, etc)
                }
            }
        }, 
        "wasm_dependencies": {              // WebAssembly dependencies in this package 
            "files_with_wasm": [            // Relative path to files with WebAsssembly (rooted at the package directory)
                "file.wasm"                 
            ],
            "wasm_in_source": [             // Relative path to WebAssembly files in source code of the package 
                "file.wasm"
            ],
            "wasm_in_dependencies": [       // Packages that WebAssembly exists in (statically determined) 
                "dependent_package_name"
            ],
            "dependency_tree": {            // Dependency tree between packages that WebAssembly exists in. 
                "package_name": [package_name], 
                "package_name": []
            }
        }
    }
} 
```

