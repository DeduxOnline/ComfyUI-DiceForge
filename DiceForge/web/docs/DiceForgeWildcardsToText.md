### Wildcards to Text

![Wildcards to Text filling in a prompt, shown by Preview as Text](images/wildcards_to_text.png)

One prompt field with the same syntax as CLIP Dual Text Encode (wildcards, `{a|b}` choices, variables, comments, the seed modes), and a `text` output: the prompt filled in, for any text encoder (Flux, SD3, video models), a text input, a file name or another prompt node. The same `text`, `seed` and `seed_mode` give the same text as CLIP Dual Text Encode's `positive_text`. Its field has the same tools: the `__` and tag autocomplete, syntax highlighting, and in its right-click menu the Syntax guide, Wildcard Browser and Tag Browser. `<lora:...>` tags stay in the text, for a node that reads them. Under the advanced inputs: `seed_mode` and `trim`.
