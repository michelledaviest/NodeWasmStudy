// BEGINNING-JS-TRANSFORM-MARKER-THINGY
if (WebAssembly.__realwasm_modified === undefined) {
  // This global object is shared across modules. Only modify it at runtime
  // once.
  WebAssembly.__realwasm_modified = true;

  const __realwasm_paper__log = function(...args) {
    const caller = __realwasm_paper__findCaller();
    const string_args = args.map(arg => typeof arg === "string" ? arg : JSON.stringify(arg));
    const msg = ["RealWasmLog", ...string_args, caller].join("__,__");
    console.error(msg); 
  }

  function getRandomFileName() {
    try {
      const fs = require(`fs${REQUIRE_TERMINATOR}`);
      var random = String(Math.random()).replace(".", "") + "_TODO";     
      var absolute_filename = "/home/RealWasm/docker-tmp/realwasm-module-" + random + ".wasm";
      while (fs.existsSync(absolute_filename)) {
        random = String(Math.random()).replace(".", "") + "_TODO";     
        absolute_filename = "/home/RealWasm/docker-tmp/realwasm-module-" + random + ".wasm"; 
      }
      return random  

    } catch (e) {
      try {
        import(`fs${REQUIRE_TERMINATOR}`).then(fs => {
          var random = String(Math.random()).replace(".", "") + "_TODO";     
          var absolute_filename = "/home/RealWasm/docker-tmp/realwasm-module-" + random + ".wasm";
          while (fs.existsSync(absolute_filename)) {
            random = String(Math.random()).replace(".", "") + "_TODO";     
            absolute_filename = "/home/RealWasm/docker-tmp/realwasm-module-" + random + ".wasm"; 
          }
          return random
        })
      } catch (e) {
        var random = String(Math.random()).replace(".", "") + "_TODO";     
        return random 
      }
    }
  }

  async function __realwasm_paper__hashArray(obj) { return getRandomFileName(); }
  function __realwasm_paper__hashArraySync(obj) { return getRandomFileName(); }
  
  function __realwasm_paper__findCaller() {
    const err = new Error();
    Error.captureStackTrace(err, __realwasm_paper__findCaller);
    const stack = err.stack.split('\\n');
    return JSON.stringify(stack);  
  }

  const __realwasm_paper__original_WebAssembly_Module = WebAssembly.Module;
  const __realwasm_paper__original_WebAssembly_Instance = WebAssembly.Instance;
  const __realwasm_paper__original_WebAssembly_Table = WebAssembly.Table;
  const __realwasm_paper__original_WebAssembly_Memory = WebAssembly.Memory;
  function isWasmModule(obj) {
    const proto = Object.getPrototypeOf(obj);
    return proto === __realwasm_paper__WebAssembly_Module.prototype ||
           proto === __realwasm_paper__original_WebAssembly_Module.prototype;
  }
  function isWasmInstance(obj) {
    const proto = Object.getPrototypeOf(obj);
    return proto === __realwasm_paper__WebAssembly_Instance.prototype ||
           proto === __realwasm_paper__original_WebAssembly_Instance.prototype;
  }
  function __realwasm__paper__type(arg) {
    const types = [Int8Array, Uint8Array, Uint8ClampedArray, Int16Array,
      Uint16Array, Int32Array, Uint32Array, Float32Array, Float64Array,
      BigInt64Array, BigUint64Array, ArrayBuffer, DataView
      // Using Node version 21 does not fix this error. Commenting out Response does not seem to break anything.   
      // Error in: gzuidhof/rollup-plugin-base64
      //, Response
    ];
    for (const type of types) {
      if (arg instanceof type) {
        return type.name;
      }
    }
    if (isWasmModule(arg)) {
      return "WebAssembly.Module";
    }
    if (isWasmInstance(arg)) {
      return "WebAssembly.Instance";
    }
    if (arg === undefined) {
      return "undefined";
    }
    if (arg === null) {
      return "null";
    }
    return "Unknown";
  }
  function __realwasm__paper__setWrapper(idx, val) {
    __realwasm_paper__log("ExportTableSet");
    return __realwasm_paper__original_WebAssembly_Table.prototype.set.call(this, idx, val);
  }
  function __realwasm__paper__make_getWrapper(hash) {
    function __realwasm__paper__getWrapper(idx) {
      const obj = __realwasm_paper__original_WebAssembly_Table.prototype.get.call(this, idx);
      if (!(obj instanceof Function)) {
        return obj;
      }
      return (...args) => {
        __realwasm_paper__log("WebAssemblyCallTableExport",hash,idx);
        return obj(...args);
      };
    }
    return __realwasm__paper__getWrapper;
  }
  function __realwasm__paper__setWrapperImport(idx, val) {
    __realwasm_paper__log("ImportTableSet");
    return __realwasm_paper__original_WebAssembly_Table.prototype.set.call(this, idx, val);
  }
  function __realwasm__paper__make_getWrapperImport(hash) {
    function __realwasm__paper__getWrapper(idx) {
      const obj = __realwasm_paper__original_WebAssembly_Table.prototype.get.call(this, idx);
      if (!(obj instanceof Function)) {
        return obj;
      }
      return (...args) => {
        __realwasm_paper__log("WebAssemblyCallTableImport",hash,idx);
        return obj(...args);
      };
    }
    return __realwasm__paper__getWrapper;
  }
  function __realwasm__paper__hookImports(importGroups, hash) {
    const result = {}
    if (importGroups === null || importGroups === undefined) {
      return importGroups
    }
    for (const [groupName, group] of Object.entries(importGroups)) {
      const newGroup = {};
      for (const [importName, import_] of Object.entries(group)) {
        if (import_ === null || import_ === undefined) {

        } else {
          const import_type_name = import_.constructor.name;
          if (import_type_name === "Number") {
            __realwasm_paper__log("WebAssemblyImport",hash,groupName,importName,import_type_name,import_);
          } else {
            __realwasm_paper__log("WebAssemblyImport",hash,groupName,importName,import_type_name);
          }  
        }
        newGroup[importName] = import_;
        if (import_ instanceof __realwasm_paper__original_WebAssembly_Table) {
          import_.set = __realwasm__paper__setWrapperImport;
          import_.get = __realwasm__paper__make_getWrapperImport(hash);
        } else if (import_ instanceof Function) {
          // Overwrite it with hooked function
          newGroup[importName] = (...args) => {
            __realwasm_paper__log("WebAssemblyCallImport",hash,groupName,importName);
            return import_(...args);
          };
        } else if (import_ instanceof __realwasm_paper__original_WebAssembly_Memory) {
          // Returning a Proxy and even logging accesses to attributes such as
          // buffer doesn't seem to work.
        }
      }
      result[groupName] = newGroup;
    }
    return result;
  }
  function __realwasm__paper__hookWasmResultObject(instance, hash) {
    for (const export_name in instance.exports) {
      const export_ = instance.exports[export_name];
      if (export_ instanceof __realwasm_paper__original_WebAssembly_Table) {
        export_.set = __realwasm__paper__setWrapper;
        export_.get = __realwasm__paper__make_getWrapper(hash);
      }
    }
    const memo = {};
    const old_exports = instance.exports;
    const exports = new Proxy(memo, {
      get(target, name) {
        const export_ = old_exports[name];
        if (export_ instanceof Function) {
          if (!(name in memo)) {
            memo[name] = (...args) => {
              // Assumes no use of table.set; will raise exception on table.set
              // because this is not a valid WebAssembly function. To date we
              // have luckily not found any uses of table.set.
              __realwasm_paper__log("WebAssemblyCallExport",export_.moduleHash,name);
              return export_(...args);
            }
            export_.moduleHash = hash;
          }
          return memo[name];
        }
        return export_;
      }
    });
    return new Proxy(instance, {
      get(target, name) {
        __realwasm_paper__log("WebAssemblyLoadInstanceAttr",hash,name);
        if (name === "exports") {
          return exports;
        }
        return target[name];
      }
    });
  }
  function dumpCompiledWasm(buffer, hash) {
    
    function errorDumpCompiledWasm(hash, e) {
      __realwasm_paper__log("ErrorDumpingCompiledWasm", hash, e.stack, e.name, e.message);
    }

    const REQUIRE_TERMINATOR = ''
    try {
      const fs = require(`fs${REQUIRE_TERMINATOR}`);
      const path = require(`path${REQUIRE_TERMINATOR}`);
      const filename = path.join("/home/RealWasm/docker-tmp/realwasm-module-" + hash + ".wasm").trim();
      fs.writeFileSync(filename, Buffer.from(buffer));
      __realwasm_paper__log("DumpCompiledWasm",filename);
    } catch (e) {
      try {
        import(`fs${REQUIRE_TERMINATOR}`).then(fs => {
            import(`path${REQUIRE_TERMINATOR}`).then(path => {
              const filename = path.join("/home/RealWasm/docker-tmp/realwasm-module-" + hash + ".wasm").trim();
              fs.writeFileSync(filename, Buffer.from(buffer));
              __realwasm_paper__log("DumpCompiledWasm",filename);    
            })
            .catch(e => { errorDumpCompiledWasm(hash, e)})
        })
        .catch(e => { errorDumpCompiledWasm(hash, e) })
      } catch (e) {
        errorDumpCompiledWasm(hash, e)
      }
    }
  }
  WebAssembly.compile = (function (orig) {
    return async function (...args) {
      __realwasm_paper__log("WebAssemblyCompile");
      __realwasm_paper__log("WebAssemblyCompileWithType",__realwasm__paper__type(args[0]));
      const hash = await __realwasm_paper__hashArray(args[0]);
      dumpCompiledWasm(args[0], hash);
      __realwasm_paper__log("WebAssemblyCompileWithHash",hash);
      const __realwasm_paper__module = await orig(...args);
      __realwasm_paper__module.__realwasm_paper_hash = hash;
      return __realwasm_paper__module;
    };
  })(WebAssembly.compile);
  WebAssembly.compileStreaming = (function (orig) {
    return async function (...args) {
      __realwasm_paper__log("WebAssemblyCompileStreaming");
      __realwasm_paper__log("WebAssemblyCompileStreamingWithType",__realwasm__paper__type(args[0]));
      const sourceResponse = await args[0];
      const source = new Uint8Array(await sourceResponse.clone().arrayBuffer());
      const hash = await __realwasm_paper__hashArray(source);
      dumpCompiledWasm(source, hash);
      __realwasm_paper__log("WebAssemblyCompileStreamingWithHash",hash);
      return orig(...args).then((module) => {
        module.__realwasm_paper_hash = hash;
        return module;
      });
    };
  })(WebAssembly.compileStreaming);
  WebAssembly.instantiate = (function (orig) {
    return async function (module, importObject) {
      __realwasm_paper__log("WebAssemblyInstantiate");
      __realwasm_paper__log("WebAssemblyInstantiateWithType",__realwasm__paper__type(module));
      if (isWasmModule(module)) {
        if (module.__realwasm_paper_hash === null || module.__realwasm_paper_hash === undefined) {
          module.__realwasm_paper_hash = __realwasm_paper__hashArraySync(module);
          const hash = module.__realwasm_paper_hash;
          const source = new Uint8Array(await module.clone().arrayBuffer());
          dumpCompiledWasm(source, hash); 
        } 
        const hash =  module.__realwasm_paper_hash; 
        __realwasm_paper__log("WebAssemblyInstantiateWithHash",hash);
        importObject = __realwasm__paper__hookImports(importObject, hash);
        const instance = await orig(module, importObject);
        return __realwasm__paper__hookWasmResultObject(instance, hash);
      }
      // It's bytes and results in a Result
      const hash = await __realwasm_paper__hashArray(module);
      __realwasm_paper__log("WebAssemblyInstantiateWithHash",hash);
      dumpCompiledWasm(module, hash);
      importObject = __realwasm__paper__hookImports(importObject, hash);
      const result = await orig(module, importObject);
      result.instance = __realwasm__paper__hookWasmResultObject(result.instance, hash);
      return result;
    };
  })(WebAssembly.instantiate);
  WebAssembly.instantiateStreaming = (function (orig) {
    // instantiateStreaming requires either a Response or a Promise<Response>
    // (both containing raw bytes), so we don't have to think about
    // Module/bytes distinction here.
    return async function (originalSource, importObject) {
      __realwasm_paper__log("WebAssemblyInstantiateStreaming");
      __realwasm_paper__log("WebAssemblyInstantiateWithType",__realwasm__paper__type(originalSource));
      const sourceResponse = await originalSource;
      const source = new Uint8Array(await sourceResponse.clone().arrayBuffer());
      const hash = await __realwasm_paper__hashArray(source);
      dumpCompiledWasm(source, hash);
      __realwasm_paper__log("WebAssemblyInstantiateWithHash",hash);
      importObject = __realwasm__paper__hookImports(importObject, hash);
      const result = await orig(sourceResponse, importObject);
      result.module.__realwasm_paper_hash = hash;
      result.instance = __realwasm__paper__hookWasmResultObject(result.instance, hash);
      return result;
    };
  })(WebAssembly.instantiateStreaming);
  class __realwasm_paper__WebAssembly_Module extends __realwasm_paper__original_WebAssembly_Module {
    static [Symbol.hasInstance](obj) {
      return isWasmModule(obj);
    }
    constructor(...args) {
      __realwasm_paper__log("WebAssemblyModule");
      __realwasm_paper__log("WebAssemblyCreateModuleWithType",__realwasm__paper__type(args[0]));
      const hash = __realwasm_paper__hashArraySync(args[0]);
      dumpCompiledWasm(args[0], hash);
      __realwasm_paper__log("WebAssemblyCreateModuleWithHash",hash);
      super(...args);
      // Store the hash on the module object so we can use it later in the actual
      // instantiation.
      this.__realwasm_paper_hash = hash;
    }
  }
  WebAssembly.Module = __realwasm_paper__WebAssembly_Module;
  class __realwasm_paper__WebAssembly_Instance extends __realwasm_paper__original_WebAssembly_Instance {
    static [Symbol.hasInstance](obj) {
      return isWasmInstance(obj);
    }
    constructor(module, importObject) {
      const hash = module.__realwasm_paper_hash;      
      __realwasm_paper__log("WebAssemblyInstance");
      __realwasm_paper__log("WebAssemblyInstantiateWithType",__realwasm__paper__type(module));
      __realwasm_paper__log("WebAssemblyInstantiateWithHash",hash);
      importObject = __realwasm__paper__hookImports(importObject, hash);
      super(module, importObject);
    __realwasm__paper__hookWasmResultObject(this, hash);
    }
  }
  WebAssembly.Instance = __realwasm_paper__WebAssembly_Instance;
  const __realwasm_paper_OldWasm = WebAssembly;
  const __realwasm_paper_hasLoaded = {};
  WebAssembly = new Proxy(__realwasm_paper_OldWasm, {
    get(target, name) {
      if (__realwasm_paper_hasLoaded[name] === undefined) {
        __realwasm_paper__log("WebAssemblyLoadAttr",name);
        __realwasm_paper_hasLoaded[name] = true;
      }
      return target[name];
    }
  });  
  process.exit = function(){}
}
// END-JS-TRANSFORM-MARKER-THINGY

