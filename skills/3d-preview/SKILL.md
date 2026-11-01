---
name: 3d-preview
description: Interactive 3D build preview as a single HTML page (three.js) with dimension lines, numbered parts, a parts list, printed parts with time and grams, and build steps. Use as soon as the concept of anything assembled from several parts (frame, mechanism, mount, prop) is roughly clear, and update it on every design change.
---

# 3D build preview

The user wants to rotate the build and see the dimensions right away, not read text. Make one self-contained HTML page and keep updating the same file.

## When
- As soon as the concept is roughly clear, even with assumptions. Write the assumptions on the page; do not wait for every answer.
- On every design change, update the page. In the Claude app publish it as an artifact and republish to the same URL; elsewhere open the file in a browser.

## Where
- Next to the project, e.g. `<project>/preview.html`. Note the link or path in the project README.
- Generators export meshes for the page as JSON (`{"v": [...], "f": [...]}`), because an artifact cannot serve `.stl` files.

## What the page contains
1. **3D scene**: three.js via importmap from a pinned CDN version (e.g. `https://cdn.jsdelivr.net/npm/three@0.160.0/`), OrbitControls, CSS2DRenderer.
   - Surroundings at real scale (wall, table, roof, pipe) when the part attaches to something.
   - Parts coloured by material (printed, bought tube, wood, fabric) so the colour square in the list matches the 3D.
   - **Numbered labels** on parts, the same numbers in the side list. Hovering a list item highlights the part.
   - **Dimension lines** (lines + labels), toggled by a button.
   - Mode switch (e.g. Frame / Frame + cover) and views (3D / Front / Side).
2. **Side list of parts**: number, name, material (colour square), size, purpose.
3. **Cards under the model**: main dimensions, cutting plan for bought material, printed parts (count, size, time and grams from the slicer), numbered build steps in real order, open questions.
4. **Joints close up** for printed joints: a 3D detail in mm with a switch "As printed" / "Assembled".

## Rules
- **Compute dimensions from the scene geometry** (curve lengths, heights, bounding box of flat parts in their best bed orientation) and fill them into the HTML through `data-v` attributes, so the text and the model never drift apart. Keep fixed cut lengths as constants in one object.
- Check that every printed part fits the bed; if not, split it and say so on the page.
- Design from material the user has at home.
- Check the page once before publishing: one screenshot and the console. Expose key values as `window.__preview` and copy them into the README.

## Known pitfalls
- **CSS2D labels:** never put `transition`/`transform` on the element CSS2DRenderer moves, or labels drift away from the model. Animate an inner element.
- **Lights:** a strong coloured light overrides the material colours. Use a neutral hemisphere light (~1.5) and keep coloured spots weak.
- A `CSS2DObject` does not hide with its hidden parent group; set label and dimension visibility by hand.
- Put the camera close so the build fills the view, otherwise the parts look tiny.

## Next
- Printed parts are modelled in a generator and prepared with the `3d-print-design` skill (printcheck, minimal test, 3MF).
