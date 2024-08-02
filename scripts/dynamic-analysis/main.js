'use strict'




const fs = require('fs');
const path = require('path');
const assert = require('assert');
(async () => {
  const filename = path.format({ dir: __dirname, name: "main.wasm"});
  const binary = fs.readFileSync(filename);
  const memory = new WebAssembly.Memory({ initial: 1, maximum: 1, shared: false });
  const shared_memory = new WebAssembly.Memory({ initial: 1, maximum: 1, shared: true });
  const importObject = {
    'host': {
      'print': arg => {
        console.log(arg);
      },
      'an_int': 42,
      'a_double': 123.5,
      'memory': memory,
      'shared_memory': shared_memory,
    }
  };
  {
    const result = await WebAssembly.compile(binary);
    const instance = await WebAssembly.instantiate(result, importObject);
    instance.exports.main();
    // instance.exports.myTable.set(0, instance.exports.export2);
  }
  {
    // Note that this causes some random (large! unrelated!) WebAssembly module
    // to be compiled, just while creating the Blob/Response.
    const source = new Response(new Blob([binary], { type: 'application/wasm' }));
    const result = await WebAssembly.compileStreaming(source);
    const instance = await WebAssembly.instantiate(result, importObject);
    instance.exports.main();
  }
  {
    const result = await WebAssembly.instantiate(binary, importObject);
    result.instance.exports.main();
  }
  {
    const buffer = new ArrayBuffer(binary.length);
    const view = new Uint8Array(buffer);
    for (let i = 0; i < binary.length; i++) {
      view[i] = binary[i];
    }
    const result = await WebAssembly.instantiate(buffer, importObject);
    result.instance.exports.main();
  }
  {
    // Note that this causes some random (large! unrelated!) WebAssembly module
    // to be compiled, just while creating the Blob/Response.
    const source = new Response(new Blob([binary], { type: 'application/wasm' }));
    const result = await WebAssembly.instantiateStreaming(source, importObject);
    result.instance.exports.main();
  }
  {
    const instance = await WebAssembly.instantiateStreaming("main.wasm", importObject);
    result.instance.exports.main();
  }
  {
    const module = new WebAssembly.Module(binary);
    const instance = new WebAssembly.Instance(module, importObject);
    instance.exports.main();
  }
  {
    const module = new WebAssembly.Module(binary);
    assert(module instanceof WebAssembly.Module);
    const instance = new WebAssembly.Instance(module, importObject);
    assert(instance instanceof WebAssembly.Instance);
    const hooked = await WebAssembly.instantiate(binary, importObject);
    assert(hooked.instance instanceof WebAssembly.Instance);
    assert(hooked.module instanceof WebAssembly.Module);
  }
  // Change the function entry in the table.
  // TODO(max): Don't do this until we can figure out how to create WebAssembly
  // functions out of thin air with the right types. Since we wrap the
  // WebAssembly functions in JS functions to do dynamic analysis, table.set
  // will fail noisily.
  // result.instance.exports.myTable.set(0, result.instance.exports.export2);
})();
