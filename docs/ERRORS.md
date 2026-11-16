# Diagnostic codes

Every compiler message that has a stable code is listed here. The codes come
from `compiler/error_codes.py`, which also powers `anvil.py --explain CODE`;
this page is generated from that table by `tools/gen_error_codes_doc.py`, so
the two cannot drift.

| Code | Error | Cause | Fix |
| --- | --- | --- | --- |
| `ANV101` | unknown name | A bare name is not a value. The compiler treats an unquoted word as a value that must already exist, and nothing with that name is in scope. | Read a variable with var(name), or call a function with call fn(name, ...). If the name is a typo, the message usually suggests the closest match. |
| `ANV102` | unknown variable | The variable is read before it has ever been assigned, so no storage exists for it. | Assign it first with set var(name) = value. Function parameters are already variables; locals declared with set local(name) need local(name) to read them. |
| `ANV103` | unknown local variable | local(name) refers to a function-local binding that this function never declares. | Declare it with set local(name) = value before reading it. Locals are per call and do not survive a return. |
| `ANV104` | unknown function | A call names a function that is not declared anywhere in the program or its includes. | Check the spelling, or declare the function with fn(name) before calling it. Includes must be listed at the top of the file. |
| `ANV105` | wrong argument count | The function was declared with a different number of parameters than this call passes. | Pass exactly the declared number of arguments, or change the declaration. The message states both counts. |
| `ANV106` | unclosed block | A block was opened (fn, if, while, for) and never closed, so the parser ran out of file while still inside it. | Add the missing end for the block named in the message. Indentation does not close blocks in Anvil. |
| `ANV107` | unterminated text | A text literal was opened with a quote and the line ended before the closing quote. | Close the string. Supported escapes are \n, \t, \" and \\; a raw newline cannot appear inside one line. |
| `ANV108` | non-finite number | A numeric literal or computed value is NaN or infinite, which Anvil rejects so comparisons stay meaningful. | Use a finite literal, or guard the division/modulo that produced it. Anvil numbers are IEEE-754 doubles. |
| `ANV109` | statement outside a function | A statement that needs a function body was written at top level. | Move the statement into fn(main) or another function. Top level accepts configuration, arrays, enums, includes, initial values and calls. |
| `ANV110` | no entry function | The program has no functions at all, so there is nothing to run. | Add fn(main) with the program's statements and end with call fn(main). |

Ask the compiler about one code:

```
python compiler/anvil.py --explain ANV102
```

Messages without a code are either internal checks or one-off diagnostics;
they still carry `path:line` and a caret, and `--diagnostics editor` adds a
column for editor integration.
