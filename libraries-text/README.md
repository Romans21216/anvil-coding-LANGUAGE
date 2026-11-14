# text

String helpers that the builtins do not cover. Import by name:

```
library import text
```

| function | result |
|---|---|
| `pad-right(text, width)` | spaces appended until the text is `width` long |
| `center(text, width)` | spaces on both sides |
| `capitalize(text)` | first letter upper, the rest untouched |
| `index-of(text, needle)` | position of the first match, or `-1` |
| `count-words(text)` | words separated by spaces, tabs, newlines or carriage returns |
| `is-palindrome(text)` | `1` when it reads the same backwards |
| `left-of(text, separator)` | everything before the first separator (the whole text if absent) |
| `right-of(text, separator)` | everything after it (empty if absent) |

Builtins already cover `upper`, `lower`, `trim`, `mid`, `len`, `contains`,
`starts_with` and `ends_with`; this library adds what they don't.

## Worth knowing

- Everything here is reentrant: `pad-right` and `center` recurse (bounded by the
  256-character text limit) instead of accumulating in a global, and
  `is-palindrome` compares mirrored characters.
- `index-of` compares text slices, so it finds substrings, not characters only.
- `left-of` / `right-of` split on the **first** separator; nothing here parses
  every field.
