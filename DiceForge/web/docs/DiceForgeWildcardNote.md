### Wildcard Note

A note, like ComfyUI's **Note**, for the lines of a wildcard: write them while you work, with the prompt fields' tools (the `__` and tag autocomplete, syntax highlighting, and the Syntax guide, Wildcard Browser and Tag Browser in its right-click menu), and **💾 Save to WildCard** puts them into a wildcard file. It is not run with the workflow.

- `text`: the lines, one per line. Each is trimmed, and empty lines and repeats are left out.
- `wildcard`: the wildcard they go to (a txt file, or a yaml key: into its yaml file, which keeps its comments), or **＋ New file…**, which asks for a name (folders with `/`, for example `outfit/dress`). The list follows the files made, renamed and deleted in the Wildcard Browser; **↻ Refresh the file list** in the right-click menu reads the wildcards folders again, after a file was added by hand.
- `mode`: **add lines** puts the note's lines after the file's, leaving out the lines the file already has (its comments stay); **replace file** puts them in place of the file's lines, after asking.

A name without a file makes that file. After a save, the list points at the file saved, so the next lines go to the same file.
