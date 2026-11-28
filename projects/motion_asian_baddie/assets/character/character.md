# Character notes

Source: Pinterest pin 1126322188118496502
Original: `source.jpg`, 564x1002, seated bust shot, beige wall, dark brown leather armchair, small Japanese watermark top-right.

## What is fixed

- Short black bob, thick straight bangs, side pieces at the cheeks
- Round soft face, fair skin, dark brown eyes, full lips
- Curvy build: extremely large bust with deep cleavage, wide hips, thick thighs
- Two separate pieces: tight grey scoop-neck t-shirt + grey high-waist bodycon mini skirt
- Small silver hoops

## What is NOT fixed

- Hair length beyond the bob
- Exact top and skirt cut (the source is seated, fabric folds hide the hem)
- Footwear (not visible in the source; default to bare legs and simple black heels unless a clip needs otherwise)

## Prompt rules

- Use `character.json` as the only source of the identity sentence.
- Change one view sentence at a time; keep outfit/style identical across views.
- Do not add makeup or jewelry details that are not in the spec; they drift between views.
- If a clip needs a different outfit, add it to the idea's `research.md` and generate a separate reference. Do not edit the master spec mid-project.

## Generated files

- `sheet_front.png`, `sheet_face.png`: Z-Image Turbo (uncensored), 768x1344
- `sheet_three_quarter.png`, `sheet_side.png`, `sheet_back.png`: Wan 2.2 I2V turntable, 480x832
- `turntable.mp4`: source orbit clip
- `sheet_contact.jpg`: labelled 6-panel sheet
- `character.png`: default Animate reference

## Known issues

- The source is AI-looking and very smooth; generated sheets can go plastic. Keep "realistic skin texture" in the style string and review at 100%.
- The watermark must never reach the reference image.
- Full-body views may invent footwear or change the skirt length; check before picking.
- Generated bust is large but still smaller than the pin. Pushing harder makes it cartoonish.
- Z-Image does not follow side/back prompts at cfg 1; use the Wan turntable for those views.
