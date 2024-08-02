"use strict";

// node transform.js main.js
const fs = require('fs/promises');
const path = require('path');
const assert = require('assert');
assert(process.argv.length > 2, "Please provide a file to transform");
const inFile = process.argv[process.argv.length - 1];
const parsed = path.parse(inFile);
const outFile = path.format({ dir: parsed.dir, name: `${parsed.name}`, ext: parsed.ext });

function hasShebang(buf) {
  // From https://github.com/nodejs/help/issues/988#issuecomment-346940560
  const NULL = 0x00;
  const BOM_UTF16LE = [0xFF, 0xFE];
  const BOM_UTF8 = [0xEF, 0xBB, 0xBF];
  const SHEBANG = [0x23, 0x21]; // #!
  // UTF16LE with BOM: FF FE 23 00 21 00
  if (buf.length >= 6 && buf[0] === BOM_UTF16LE[0] && buf[1] === BOM_UTF16LE[1]) {
    return buf[2] === SHEBANG[0] && buf[3] === NULL &&
           buf[4] === SHEBANG[1] && buf[5] === NULL;
  }
  // UTF8 with BOM: EF BB BF 23 21
  if (buf.length >= 5 && buf[0] === BOM_UTF8[0] && buf[1] === BOM_UTF8[1] && buf[2] === BOM_UTF8[2]) {
    return buf[3] === SHEBANG[0] && buf[4] === SHEBANG[1];
  }
  // UTF8 without BOM or ASCII: 23 21
  return buf.length >= 2 && buf[0] === SHEBANG[0] && buf[1] === SHEBANG[1];
}

function hasUseStatement(buf){
  const NULL = 0x00;
  const BOM_UTF16LE = [0xFF, 0xFE];
  const BOM_UTF8 = [0xEF, 0xBB, 0xBF];  
  const SINGLE_QUOTE = 0x27;      // hex of '
  const DOUBLE_QUOTE = 0x22;      // hex of "
  const USE = [0x75, 0x73, 0x65]; // hex of use

  // UTF16LE with BOM: FF FE 23 00 27|22 75 73 65
  if (buf.length >= 8 && buf[0] === BOM_UTF16LE[0] && buf[1] === BOM_UTF16LE[1]) {
    return (buf[2] === SINGLE_QUOTE || buf[2] === DOUBLE_QUOTE) && buf[3] == NULL &&     
            buf[4] === USE[0] && buf[5] === NULL &&
            buf[6] === USE[1] && buf[7] === NULL && 
            buf[8] === USE[2] && buf[9] === NULL;
  }
  // UTF8 with BOM: EF BB BF 27|22 75 73 65
  if (buf.length >= 7 && buf[0] === BOM_UTF8[0] && buf[1] === BOM_UTF8[1] && buf[2] === BOM_UTF8[2]) {
    return (buf[3] === SINGLE_QUOTE || buf[3] === DOUBLE_QUOTE) && buf[4] === USE[0] && buf[5] === USE[1] && buf[6] === USE[2];
  }
  // UTF8 without BOM or ASCII: 27|22 75 73 65
  return buf.length >= 4 && (buf[0] === SINGLE_QUOTE || buf[0] === DOUBLE_QUOTE) && buf[1] === USE[0] && buf[2] === USE[1] && buf[3] === USE[2];  
}

(async () => {
  let result = await fs.readFile(inFile);
  const fd = await fs.open(outFile, "w+");
  if (hasShebang(result)) {
    const newlinePos = result.indexOf("\n");
    const shebangLine = result.slice(0, newlinePos);
    await fd.writeFile(shebangLine);
    await fd.writeFile("\n");
    result = result.slice(newlinePos);
  }
  if (hasUseStatement(result)) {
    const newlinePos = result.indexOf("\n");
    const useStmtLine = result.slice(0, newlinePos);
    await fd.writeFile(useStmtLine);
    await fd.writeFile("\n");
    result = result.slice(newlinePos);
  }
  const filename = path.format({ dir: __dirname, name: "tracing.js"});
  const tracing_code = await fs.readFile(filename);
  await fd.writeFile(tracing_code);
  await fd.writeFile(result);
  await fd.close();
})();