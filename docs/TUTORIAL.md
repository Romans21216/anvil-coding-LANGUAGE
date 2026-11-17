# Learn Anvil in ten short programs

Every lesson is a real file in `examples/tutorial/`, and every file is built and
run by `tests/test_tutorial.py` on both backends, so the output below is checked,
not aspirational.

Run a lesson with either backend:

```powershell
python compiler/anvil.py examples/tutorial/01_hello.ANVL -o build/hello.exe
python compiler/anvil.py examples/tutorial/01_hello.ANVL --backend native -o build/hello.exe
```

Want the smallest possible first success? This builds and runs a greeting with
no files at all:

```powershell
python compiler/anvil.py --hello
```

Or try lines live in the shell — it remembers your variables:

```powershell
python compiler/anvil.py --repl
anvil> name = "Ada"
name = Ada
anvil> say "Hello, " & name
Hello, Ada
```

---

## 1. Say hello

`examples/tutorial/01_hello.ANVL`

```anvil
fn(main)
  say "Hello, world!"
  say "This is Anvil."
end
call fn(main)
```

`say` prints one line. Every program runs `fn(main)`, reached by `call fn(main)`.

## 2. Numbers and arithmetic

`examples/tutorial/02_numbers.ANVL`

```anvil
fn(main)
  set var(score) = 10
  add var(score) 5
  say "Score: " & var(score)
  say 3 + 4 * 2
  say (3 + 4) * 2
  say 7 % 3
end
call fn(main)
```

Output:

```
Score: 15
11
14
1
```

`set` stores, `add` changes in place, `&` joins text and numbers, and `%` is the
remainder (7 % 3 is 1). Multiplication happens before addition, as in maths.

## 3. Text

`examples/tutorial/03_text.ANVL`

```anvil
fn(main)
  set var(name) = "ada"
  say "Hello, " & upper(var(name)) & "!"
  say len(var(name))
  say lower("LOUD")
end
call fn(main)
```

`upper`, `lower` and `len` are the everyday text tools. Quotes make text;
unquoted words are numbers, variables and keywords.

## 4. Decisions

`examples/tutorial/04_decisions.ANVL`

```anvil
fn(main)
  set var(age) = 15
  if var(age) >= 18
    say "adult"
  elif var(age) >= 13
    say "teen"
  else
    say "child"
  end
  if not var(age) = 15
    say "unexpected"
  end
end
call fn(main)
```

`if` runs a block when the test holds, `elif` checks another test, `else` is the
fallback, and `end` closes the whole chain. `not` flips a test.

## 5. Repetition

`examples/tutorial/05_loops.ANVL`

```anvil
fn(main)
  repeat 3
    say "hip"
  end
  for local(index) = 1 to 3
    say "count " & local(index)
  end
  set var(n) = 3
  while var(n) > 0
    say var(n)
    add var(n) -1
  end
end
call fn(main)
```

`repeat` runs a block a fixed number of times, `for` walks a range, and `while`
keeps going while its test holds.

## 6. Your own functions

`examples/tutorial/06_functions.ANVL`

```anvil
fn(double, value)
  output var(value) * 2
end

fn(main)
  say call fn(double, 21)
  say call fn(double, 3.5)
end
call fn(main)
```

`output` sends a value back to the caller. Functions return numbers; the name
inside the brackets after `fn(` is how you call it.

## 7. Arrays

`examples/tutorial/07_arrays.ANVL`

```anvil
array scores(3)

fn(main)
  set array(scores, 0) = 10
  set array(scores, 1) = 20
  set array(scores, 2) = 30
  set var(total) = 0
  for local(index) = 0 to 2
    add var(total) array(scores, local(index))
  end
  say "Total: " & var(total)
end
call fn(main)
```

`array scores(3)` reserves three slots, numbered 0 to 2. `array(scores, i)` reads
or writes one slot, and Anvil stops with a clear error if `i` is out of range.

## 7b. Lists that grow

Arrays have a fixed size. A list grows as you add to it:

```anvil
list scores

fn(main)
  add scores 10
  add scores 20
  add scores 30
  say count(scores)
  say array(scores, 1)
end
call fn(main)
```

`count(scores)` is 3 and `array(scores, 1)` is 20. Lists hold up to 256 values;
adding past that stops with a bounds error rather than corrupting memory.

## 8. Asking the player

`examples/tutorial/08_input.ANVL`

```anvil
fn(main)
  ask "What is your name? ", var(name)
  say "Hello, " & trim(var(name)) & "!"
end
call fn(main)
```

`ask` reads one typed line into a text variable; this is the whole "greeting
program" beginners expect. If the variable already holds a number
(`set var(age) = 0` first), `ask` reads a number instead.

## 9. The text toolkit

`examples/tutorial/09_strings.ANVL`

```anvil
fn(main)
  set var(word) = "  Beginner  "
  say "[" & trim(var(word)) & "]"
  say left("Anvil", 3)
  say right("Anvil", 3)
  say mid("Anvil", 2, 2)
  say char("Anvil", 0)
  say number("42") + 8
end
call fn(main)
```

Output:

```
[Beginner]
Anv
vil
vi
A
50
```

`trim` drops the spaces around text, `left`/`right` take from either end, `mid`
takes a slice, `char` picks one character (counting from 0), and `number` turns
text into a number.

## 10. Putting it together

`examples/tutorial/10_program.ANVL`

```anvil
fn(is_even, n)
  if var(n) % 2 = 0
    output 1
  end
  output 0
end

fn(main)
  for local(index) = 1 to 4
    set var(flag) = call fn(is_even, local(index))
    if var(flag) = 1
      say local(index) & " is even"
    else
      say local(index) & " is odd"
    end
  end
end
call fn(main)
```

This is the shape of most programs: a helper that answers a question with a
number, and a main that uses the answer.

## Returning text

Functions can hand back text too, and the result joins, compares and stores like
any other text value:

```anvil
fn(greet, who)
  output "Hello, " & var(who)
end

fn(main)
  say call fn(greet, "Ada")
end
call fn(main)
```

Both backends return text the same way, so the program above builds and runs
with `--backend native` too.

---

## Where to go next

- `examples/loops.ANVL`, `examples/functions.ANVL` and `examples/arrays.ANVL` go deeper.
- `examples/native_2d.ANVL` opens a window and draws; add `--backend native` to build it with Anvil's own compiler.
- `docs/COMPILER.md` explains the two backends and the error format.
