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
| `count-words(text)` | words separated by single spaces |
| `is-palindrome(text)` | `1` when it reads the same backwards |
| `left-of(text, separator)` | everything before the first separator (the whole text if absent) |
| `right-of(text, separator)` | everything after it (empty if absent) |

Builtins already cover `upper`, `lower`, `trim`, `mid`, `len`, `contains`,
`starts_with` and `ends_with`; this library adds what they don't.

## Worth knowing

- `pad-right` and `center` keep their result in a **global** because a local can
  hold a number but not text. They are **not reentrant**. `is-palindrome` now
  compares mirrored characters instead of building the reverse, so it is.
- `index-of` compares text slices, so it finds substrings, not characters only.
- `left-of` / `right-of` split on the **first** separator; nothing here parses
  every field.
