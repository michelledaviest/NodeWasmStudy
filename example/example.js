const fs = require('fs');
const binary = fs.readFileSync("example.wasm");

(async () => {
    let importObject = {
        'host': {
            'print': arg => {
                console.log(arg);
            },
    }};
    let result = await WebAssembly.compile(binary);
    let instance = await WebAssembly.instantiate(result, importObject);
    instance.exports.main();
    instance.exports.table.get(0)(); 
})();
