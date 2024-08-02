(module
    (import "host" "print" (func $print (param i32)))
    (func $main (export "main")
        i32.const 42
        call $print
    )
    (func $foo (export "foo")
        i32.const 0
        call_indirect
    )
    (func $bar
        i32.const 23
        call $print
    )
    (func $not-reachable)
    (table $table (export "table") 2 funcref)
    (elem $table (i32.const 0) $bar $foo)
)
