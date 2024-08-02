const fs = require('fs');
const parser = require('@babel/parser'); 
const traverse = require("@babel/traverse").default;

// file passed in as argument 
if (process.argv.length < 3) {
    process.exit("Pass in file to run analysis on.")
} 

let file_name = process.argv[2]
let wasm_modules = new Map([
    ["array", []], 
    ["base64string", []]
]);

function get_array_binary_hash(arr) {
    const crypto = require('crypto');
    const sum = crypto.createHash('sha256');    
    let buf = Buffer.from(arr)
    sum.update(buf)
    return sum.digest('hex') 
}

function get_base64_binary_hash(base64_encoded_string) {
    const crypto = require('crypto');
    const sum = crypto.createHash('sha256');    
    decoded_string = atob(base64_encoded_string)
    binary_bytes = Buffer.from(decoded_string)    
    sum.update(binary_bytes)
    return sum.digest('hex')
}

fs.readFile(file_name, 'utf8', (_err, data) => {
    
    // 'sourceType: "module"'
    const ast = parser.parse(data, {
        sourceType: 'unambiguous',
        allowImportExportEverywhere: true,
        allowReturnOutsideFunction: true,
    });

    traverse(ast, {
        ArrayExpression: function(path) {

            // Check if the first few bytes of the array contain the magic bytes of wasm
            // aka /0asm, or 
            // hex: 00 61 73 6D, or,
            // decimal: 0, 97, 115, 109
            let wasmMagicBytesHex = [0x0, 0x61, 0x73, 0x6d]
            let wasmMagicBytesDecimal = [0, 97, 115, 109]
            let arr_ptr = 0;
            while(path.node.elements[arr_ptr+1] === 0) {
                arr_ptr += 1; 
            }

            let arraySlice = path.node.elements.slice(arr_ptr, arr_ptr+4).map((e) => e.value); 
            if (arraySlice.every(function(value, index) { return value === wasmMagicBytesHex[index]}) ||
                arraySlice.every(function(value, index) { return value === wasmMagicBytesDecimal[index]})
            ) {
                let new_hashmap_value = wasm_modules.get("array"); 
                new_hashmap_value.push(get_array_binary_hash(
                    path.node.elements.map((element) => element.value)))
                wasm_modules.set("array", new_hashmap_value);                    
            }
             
        },

        StringLiteral: function(path) {
            // WebAssembly can also be encoded as a base64 string starting with AGFzbQ, ie, \0asm         
            // see: https://cyberchef.org/#recipe=To_Base64('A-Za-z0-9%2B/%3D')&input=AGFzbQEAAAABBAFgAAADAgEACgcBBQBBfxoL
            // the base64 wasmBinary either shows up with AGFzbQ at the start of the string or as "data:application/octet-stream;base64,AGFzbQ..."
            // tested on 
            // - ./rxt/node_modules/wat-wasm/node_modules/binaryen/bin/wasm-opt   
            // - ./mokka/node_modules/es-module-lexer/dist/lexer.cjs

            let wasmBinaryStart = "AGFzbQ";

            let str = path.node.value; 
            if (
                (str.slice(0, 6) === wasmBinaryStart) ||
                (str.includes(',') && str.split(',')[1].slice(0, 6) === wasmBinaryStart) 
            ){
                let new_hashmap_value = wasm_modules.get("base64string"); 
                new_hashmap_value.push(get_base64_binary_hash(str))
                wasm_modules.set("base64string", new_hashmap_value); 
            } 
        }
    });

    // When done traversing AST, print out map to stdout in JSON format
    let json_wasm_modules = JSON.stringify(Object.fromEntries(wasm_modules));
    console.log(json_wasm_modules)
});