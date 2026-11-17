# validate

Predicates for text that came from a file, a prompt or a network reply. Import by
name:

```
library import validate
```

| function | `1` when |
|---|---|
| `is-empty(text)` | the text has no characters |
| `is-digit-text(text)` | every character is 0-9 and there is at least one |
| `is-alpha-text(text)` | every character is a letter A-Z or a-z |
| `is-number-text(text)` | an optional leading `-` followed by digits, at least one |
| `is-space-text(text)` | every character is a space |
| `is-upper-text(text)` | at least one letter, and no lower-case letters |

Each answers `0` or `1`, so they drop straight into `if`:

```anvl
library import validate

fn(main)
  if call fn(is-number-text, "-42")
    say "a whole number"
  end
end
```

## Worth knowing

- All six are loops over `ord(mid(...))`, so they never allocate and never touch
  a global; they are reentrant.
- `is-empty("")` is `1`, but `is-space-text("")` is `0` — an empty string has no
  characters to be spaces.
- `is-number-text` accepts whole numbers only; it does not accept `1.5`, `1e9`,
  a leading `+`, or stray spaces.
