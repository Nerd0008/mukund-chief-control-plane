# LinkedIn Image Generation

## Current image backend and interpreter

`generate_image_bytes()` uses the existing router-authorized Nano Banana 2 bridge,
`router_media.RoutedImageProvider`, with model `gemini-3.1-flash-image` and aspect ratio 4:5.
Run it with the Hermes Python interpreter; Google SDK installation is unnecessary for this
image bridge. The old `gemini-3.1-flash-lite-image` call and silent `None` failure are retired.

A failure raises its real sanitized category. `media_provider_billing` means the existing
Google project rejected generation with HTTP 402. Ask the owner to restore its billing;
do not retry repeatedly, buy credits or switch providers without authorization. Image upload
and publishing may still work for an already-approved existing image.

The independent news judge still resolves its own existing SDK-capable interpreter. This is
separate from image generation; do not install or upgrade auth libraries into Hermes to fix it.

## The medium rotation advances on every pick

`_pick_media(post_text)` writes `runtime/linkedin/image_style_state.json` as a side effect, and
`build_image_prompt()` calls it once.

Calling `_pick_media` yourself to preview the medium and then calling `build_image_prompt`
advances the rotation **twice**, so the generated image carries the *second* medium while your
preview showed the first. The preview and the artefact then disagree, and the post goes out with a
treatment nobody chose.

Rule: call `build_image_prompt()` exactly once, then read the chosen medium back from the state
file (`recent[0]`). To preview without consuming the rotation, point
`linkedin_content_gen._IMAGE_STATE` at a temporary copy of the state file first.

## The topic classifier can hand the model a banned subject

`_classify_post_topic()` buckets the post and `build_image_prompt()` puts that bucket's `concept`
on the prompt's `Subject:` line. Buckets that produce the holographic, glass-and-light look the
owner banned:

- `ai_security` fires on the ordinary phrase **`"ai model"`**, so a news post that merely mentions
  an AI model lands there and gets "a transparent glass container with subtle cracks, light
  escaping through the gaps".
- `general_cyber` and `automation` likewise default to gradient/geometric digital treatments.

`build_image_prompt(post, extra_instructions=...)` does **not** cleanly override this: the
default `Subject:` line still appears in the prompt above the override, so the model sees both and
may follow either.

Override the classifier for the run instead:

```python
import linkedin_content_gen as lcg

lcg._classify_post_topic = lambda _t: {
    "category": "custom",
    "style": "",
    "concept": "<a photographic subject that fits the post>",
}
```

This is a preview-only patch: it changes nothing on disk and no other process. Fix the bucket in
the source as a separate change, and commit it in the same terminal call (auto-stash hazard).

A subject that fits the post's physical reality beats a generic tech visual. For a post about an
unpatchable end-of-life flaw, a dusty machine opened up with a screwdriver beside it reads as real
photography and carries the argument; a glass container carrying light does not.

## Verifying the result

Load the image with `vision_analyze` and check the four things that actually matter: no rendered
text, no logos or watermarks, no neon or cyan-purple gradient or holographic interface, and real
textural imperfection (dust, scuffs, uneven light). A subject the prompt asked for and the model
produced can differ (a requested rack unit may come back as a desktop tower) — say so plainly rather
than presenting the image as exactly what was specified.
