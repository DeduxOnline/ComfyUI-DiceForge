### Danbooru Tag Enhancer

![Danbooru Tag Enhancer with its advanced inputs and the post of the last run](images/danbooru_tag_enhancer.png)

A node that makes a few tags a full prompt from a real Danbooru (or e621) post: type `1girl, hatsune miku` and get, for example, `1girl, hatsune miku, twintails, smile, thighhighs, looking at viewer, holding microphone…`, the tags of a picture that has yours, the way the anime models (Illustrious, NoobAI, Pony, Anima) learned them.

1. Type the tags to find a post with in `tags`, or connect `positive_text` of a CLIP Dual Text Encode; weights, `\(` escapes and `<lora:>` tags are read through. [Wildcards](https://github.com/DeduxOnline/ComfyUI-DiceForge#wildcard-files) and `{a|b}` choices work in `tags` too: `__characters__, 1girl` searches for a new character on every run (the node shows the tags it used). `tags`, `source`, `rating`, `mode` and `post_ids` are on the node; the rest is under *Show advanced inputs*.
   - **`source`**: where the posts come from, **danbooru** (the default; anime: Illustrious, NoobAI, Anima, Pony), **e621** (furry: NoobAI, Pony) or **safebooru** (safe anime pictures, with Danbooru's tags; no account needed). Safebooru's posts have all their tags in one list; with the Danbooru tag list downloaded, characters, series and artists are told apart (and left out unless `include_character`… are on), otherwise every tag counts as general. Each site has its own tags (`1girl` on Danbooru, `female, solo` on e621): type the site's tags, and download its [tag list](https://github.com/DeduxOnline/ComfyUI-DiceForge#tag-autocomplete-danbooru-e621) for the search to know them. e621's species tags (`fox, canine, mammal`) come with the general tags (and go with `include_appearance` off).
   - The optional **`prompt`** input takes the rest of your prompt (quality and style tags: `masterpiece, best quality…`): it goes first in `text`, is never searched, and its tags are not added again. So the search uses only the tags that say what the picture is.
2. Connect `text` to CLIP Dual Text Encode's `positive` (or another text encoder). `added_tags` has only the added ones, `post_url` the posts they came from (one link per line), `post_id` the first one's id.
3. **`mode`** works like a seed's control: **random** takes a new post on every run, like Danbooru's [random post](https://danbooru.donmai.us/posts/random), and writes it into **`post_ids`** (and the wildcards' seed into `wildcard_seed`); switch to **fixed** to keep a run you like: the posts of `post_ids` again, with the same wildcards. You can also type post ids or paste post links into `post_ids` (`4926058, https://danbooru.donmai.us/posts/123`).
4. Under its inputs the node shows the posts' pictures (click one to open the post; pictures that aren't general (on e621: safe) are blurred until clicked, unless *Blur NSFW* is off in the settings, DiceForge → Browsers), the added tags (click to copy) and what it searched. It runs also with nothing connected, just to see what it adds.

How it picks:

- Danbooru picks a random post (`/posts/random`) with the two most telling of your tags and your `rating` (a search without an account may have two tags; the rating is free): with the [tag lists](https://github.com/DeduxOnline/ComfyUI-DiceForge#tag-autocomplete-danbooru-e621) downloaded, the rarest tags Danbooru knows, characters and series first (`hatsune miku` before `1girl`), and tags it doesn't know (`masterpiece`) are left out; without the lists, or when they know none of your tags, your first two. Under the prompt the node shows what it searched (`Searched: blue_archive rating:g`). When no post has both, each tag alone.
- On e621 the search may have more tags, and all the posts come in one request (e621 asks for at most two requests a second, which the node keeps to).
- `rating`, from safe on: `general` (the default), `sensitive` (suggestive), `questionable` (nudity), `explicit`. e621 has three ratings: its safe is both `general` and `sensitive`. One of them, two next to each other (`general + sensitive`, `sensitive + questionable`, `questionable + explicit`), `up to questionable`, `sensitive and up` (everything but general), or `any`.
- **`posts`** (Advanced, 1 to 5): several posts of the search at once. Their tags go together, the ones more of the posts share first: steadier than the tags of one picture.
- From the posts, the general tags that your prompt lacks are added (`include_general`: pose, clothes, background…; characters, series and artists too, with `include_character`, `include_copyright`, `include_artist` under Advanced). Switches leave out kinds of tags, so your prompt keeps its own:

  | Switch (Advanced, on by default) | Off leaves out |
  |---|---|
  | `include_appearance` | how someone looks: hair color and style, eyes, skin, body, ears, tail, horns… |
  | `include_clothes` | clothes and accessories: shirt, skirt, uniform, thighhighs, hair ornament, glasses, also nude, barefoot… |
  | `include_background` | the scene: simple / white background, outdoors, classroom, night, cherry blossoms, on bed… |
  | `include_count` | people-count tags: 1girl, 2girls, 1boy, multiple_boys, solo, no_humans… |

  So with appearance and clothes off, your character keeps its look and outfit and the post adds the pose and scene.
- They come the most used first, at most `max_tags` (15; 0 for all), `after` or `before` your tags (`position`), written as the models learned them (spaces, escaped parentheses), without the **`exclude`** list. In `exclude`, `*` is any text: `*censor*` leaves out `bar_censor`, `censored` and `mosaic_censoring`, `*_text` every `english_text`, `japanese_text`… The default leaves out signatures, watermarks, usernames, speech bubbles, text and censoring.
- It needs Danbooru: offline, the node says so. When Danbooru is busy (503, 429: overloaded, or limiting many requests for a while), the node asks again after 1 and 3 seconds, then says so: try again in a minute.
