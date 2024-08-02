



const fs = require('fs');
const binary = fs.readFileSync("example.wasm");

(async () => {
    const importObject = {
        'host': {
            'print': arg => {
                console.log(arg);
            },
    }};

    const result = await WebAssembly.compile(binary);
    const instance = await WebAssembly.instantiate(result, importObject);
    instance.exports.main();
    //instance.exports.foo();
    //instance.exports.table.get(0)(); 
})();