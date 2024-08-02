use std::io::Read;
use anyhow::Result;
use wasmparser::{Parser, Payload::*};
use serde::{Deserialize, Serialize};

#[derive(Default, Serialize, Deserialize)]
struct WasmJSON {
    type_section: TypeSectionJSON, 
    function_section: FunctionSectionJSON, 
    import_section: ImportSectionJSON,
    export_section: ExportSectionJSON, 
    table_section: TableSectionJSON, 
    element_section: ElementSectionJSON
}

#[derive(Default, Serialize, Deserialize)]
struct TypeSectionJSON {
    count: u32
}

#[derive(Default, Serialize, Deserialize)]
struct FunctionSectionJSON {
    count: u32
}

#[derive(Default, Serialize, Deserialize)]
struct ImportSectionJSON {
    imports: Vec<ImportJSON>, 
    count_total: usize, 
    count_imported_funcs: usize, 
    imported_table: bool, 
    imported_memory: bool,     
}

impl ImportSectionJSON {
    fn add(&mut self, import: ImportJSON) {
        match import._type {
            ImportType::Table => self.imported_table = true,
            ImportType::Memory => self.imported_memory = true,
            ImportType::Function => self.count_imported_funcs += 1,
            ImportType::Global | ImportType::Tag => (),            
        }
        self.count_total += 1;
        self.imports.push(import);
    }    
}

#[derive(Serialize, Deserialize)]
struct ImportJSON {
    _type: ImportType, 
    module: String, 
    name: String, 
    internal_id: usize, 
}

#[derive(Serialize, Deserialize)]
enum ImportType {
    Table, 
    Memory, 
    Global, 
    Function, 
    Tag
}

#[derive(Default, Serialize, Deserialize)]
struct ExportSectionJSON {
    exports: Vec<ExportJSON>, 
    count_total: usize, 
    count_exported_funcs: usize, 
    exported_table: bool, 
    exported_memory: bool,     
}

impl ExportSectionJSON {
    fn add(&mut self, export: ExportJSON) {
        match export._type {
            ExportType::Table => self.exported_table = true,
            ExportType::Memory => self.exported_memory = true,
            ExportType::Function => self.count_exported_funcs += 1,
            ExportType::Global | ExportType::Tag => (),
        }
        self.count_total += 1; 
        self.exports.push(export)
    }
}

#[derive(Serialize, Deserialize)]
struct ExportJSON {
    _type: ExportType, 
    name: String, 
    internal_id: u32, 
}

#[derive(Serialize, Deserialize)]
enum ExportType {
    Table, 
    Memory, 
    Function, 
    Global, 
    Tag
}

#[derive(Default, Serialize, Deserialize)]
struct TableSectionJSON {
    tables: Vec<TableJSON>
}

#[derive(Serialize, Deserialize)]
struct TableJSON {
    initial_size: u64, 
    maximum_size: Option<u64>,  
}

#[derive(Default, Serialize, Deserialize)]
struct ElementSectionJSON { 
    elements: Vec<ElementJSON>
}

#[derive(Default, Serialize, Deserialize)]
struct ElementJSON { 
    associated_table: u32, 
    offsets: Vec<ElementSectionOffset>, 
    entries: Vec<u32>, 
    count_entries: usize, 
    count_unique_entires: usize,
}

#[derive(Serialize, Deserialize)]
enum ElementSectionOffset {
    Global{ global_index : u32 },
    Constant { value : i32 }, 
    Unknown { operator: String }
}

fn parse(mut reader: impl Read) -> Result<WasmJSON> {
    let mut buf = Vec::new();
    reader.read_to_end(&mut buf)?;
    let parser =  Parser::new(0);

    let mut wasm_json = WasmJSON::default();

    for payload in parser.parse_all(&buf) {
        match payload? {
            // Sections for WebAssembly modules
            TypeSection(reader) => wasm_json.type_section = TypeSectionJSON{
                count: reader.count(),
            },

            ImportSection(reader) => {
                let mut import_section_json = ImportSectionJSON::default();
                let (mut count_funcs_imported, mut count_table_imported, mut count_memory_imported, mut count_global_imported, mut count_tag_imported) = (0, 0, 0, 0, 0); 

                for elem in reader.into_iter() {
                    let import = elem?;
                    import_section_json.add(ImportJSON {
                        _type: match import.ty {
                            wasmparser::TypeRef::Func(_) => ImportType::Function,
                            wasmparser::TypeRef::Table(_) => ImportType::Table,
                            wasmparser::TypeRef::Memory(_) => ImportType::Memory,
                            wasmparser::TypeRef::Global(_) => ImportType::Global,
                            wasmparser::TypeRef::Tag(_) => ImportType::Tag,
                        },
                        module: import.module.to_string(),
                        name: import.name.to_string(),
                        internal_id: match import.ty {
                            wasmparser::TypeRef::Func(_) => {
                                count_funcs_imported += 1; 
                                count_funcs_imported-1
                            },
                            wasmparser::TypeRef::Table(_) => {
                                count_table_imported += 1; 
                                count_table_imported-1
                            },
                            wasmparser::TypeRef::Memory(_) => {
                                count_memory_imported += 1; 
                                count_memory_imported-1
                            },
                            wasmparser::TypeRef::Global(_) => {
                                count_global_imported += 1; 
                                count_global_imported-1
                            },
                            wasmparser::TypeRef::Tag(_) => {                            
                                count_tag_imported += 1; 
                                count_tag_imported-1
                            },                            
                        },
                    })
                }
                wasm_json.import_section = import_section_json;
            }
 
            FunctionSection(reader) => wasm_json.function_section = FunctionSectionJSON{
                count: reader.count(),
            }, 

            TableSection(reader) => { 
                let mut table_section = TableSectionJSON::default(); 
                for elem in reader.into_iter() {
                    let table = elem?;
                    table_section.tables.push(TableJSON {
                        initial_size: table.ty.initial,
                        maximum_size: table.ty.maximum,
                    })
                }
                wasm_json.table_section = table_section
            }

            ElementSection(reader) => { 
                let mut element_section = ElementSectionJSON::default();
                for elem in reader.into_iter() {
                    let elem = elem?;
                    match elem.kind {
                        wasmparser::ElementKind::Passive | 
                        wasmparser::ElementKind::Declared => (),
                        wasmparser::ElementKind::Active { table_index, offset_expr } => {

                            let mut offsets = Vec::new();
                            for op_offset in offset_expr.get_operators_reader().into_iter_with_offsets() {
                                let (op, _offset) = op_offset?;
                                match op {
                                    wasmparser::Operator::I32Const { value } => offsets.push(ElementSectionOffset::Constant { value: value }),
                                    wasmparser::Operator::GlobalGet { global_index } => offsets.push(ElementSectionOffset::Global { global_index: global_index }),                                    
                                    wasmparser::Operator::End => (), 
                                    _ => offsets.push(ElementSectionOffset::Unknown { operator: format!("{op:?}") })
                                }  
                            }

                            let entries = match elem.items{
                                wasmparser::ElementItems::Functions(functions_reader) => {
                                    let mut entries = Vec::new(); 
                                    for elem in functions_reader {
                                        let elem = elem?; 
                                        entries.push(elem);
                                    }
                                    entries                                    
                                },
                                wasmparser::ElementItems::Expressions(..) => vec![],
                            }; 

                            element_section.elements.push( ElementJSON { 
                                // If none, I think the implicit table is 0 
                                // If some, return value in Some 
                                associated_table: if let Some(table_index) = table_index {
                                    table_index
                                } else {
                                    0
                                }, 
                                offsets,                                    
                                entries: entries.clone(), 
                                count_entries: entries.clone().len(), 
                                count_unique_entires: entries.into_iter()
                                    .map(|entry| entry)
                                    .collect::<std::collections::HashSet<_>>()
                                    .len(),
                            });
                             
                        },
                    }
                }
                wasm_json.element_section = element_section; 
            }

            ExportSection(reader) => { 
                let mut export_section = ExportSectionJSON::default(); 
                for elem in reader.into_iter() {
                    let export = elem?;
                    export_section.add(ExportJSON { 
                        _type: match export.kind {
                            wasmparser::ExternalKind::Func => ExportType::Function,
                            wasmparser::ExternalKind::Table => ExportType::Table,
                            wasmparser::ExternalKind::Memory => ExportType::Memory,
                            wasmparser::ExternalKind::Global => ExportType::Global,
                            wasmparser::ExternalKind::Tag => ExportType::Tag,
                        }, 
                        name: export.name.to_string(), 
                        internal_id: export.index 
                    })   
                }
                wasm_json.export_section = export_section; 
            }

            MemorySection(_) |
            TagSection(_) |
            GlobalSection(_) |
            StartSection { .. } => {}, 
            
            // Here we know how many functions we'll be receiving as
            // `CodeSectionEntry`, so we can prepare for that, and
            // afterwards we can parse and handle each function
            // individually.
            CodeSectionStart { .. } |
            CodeSectionEntry(..) => {}

            Version { .. } |
            DataCountSection { .. } |
            DataSection(_) => {}, 

            // Sections for WebAssembly components
            ModuleSection { .. } |
            InstanceSection(_) |
            CoreTypeSection(_) |
            ComponentSection { .. } |
            ComponentInstanceSection(_) |
            ComponentAliasSection(_) |
            ComponentTypeSection(_) |
            ComponentCanonicalSection(_) |
            ComponentStartSection { .. } |
            ComponentImportSection(_) |
            ComponentExportSection(_) => {}, 

            CustomSection(_) => {}, 

            // most likely you'd return an error here
            UnknownSection { .. } => {}, 

            // Once we've reached the end of a parser we either resume
            // at the parent parser or the payload iterator is at its
            // end and we're done.
            End(_) => {}
        }
    }

    Ok(wasm_json)
}

#[test]
fn test_all_dumped_files(){
    const TEST_DIR: &str = "../../data/dumped-wasm-files";
    
    for entry in walkdir::WalkDir::new(TEST_DIR) {
        let path = entry.unwrap().path().to_owned();
        let path_str = path.as_os_str().to_string_lossy();
        if path_str.contains("invalid") || path_str.contains("issues") || path_str.contains("WasmBench") {
            continue;
        }

        if let Some("wasm") = path.extension().and_then(|os_str| os_str.to_str()) {
            if std::fs::metadata(&path).unwrap().is_file() {

                let file = std::fs::File::open(path).expect("Could not open file {}");    
                let wasm_json = parse(file); 
                assert!(wasm_json.is_ok() && serde_json::to_string(&wasm_json.unwrap()).is_ok());                 
            }
        }
    }
}

/// Get static info for WebAssembly binary
#[derive(clap::Parser, Debug)]
#[command(author, version, about, long_about = None)]
struct Args {
    /// WebAssembly binary
    #[arg(short, long)]
    binary: String,
}

fn main() {
    let _ = env_logger::try_init();
    let args = <Args as clap::Parser>::parse();   

    let file = std::fs::File::open(args.binary).expect("Could not open file {}");
    let wasm_json = parse(file).expect("msg"); 
    print!("{}", serde_json::to_string(&wasm_json).expect(""));
}