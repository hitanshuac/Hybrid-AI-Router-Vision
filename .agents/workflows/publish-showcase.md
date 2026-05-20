---
description: 
---

---
description: Automatically synthesize project logs and push updated documentation to GitHub.
---

# Publish Showcase Workflow

1. Read the current contents of `retrospective.md`, `walkthrough.md`, and `implementation_plan.md`.
2. Synthesize these files to write a comprehensive, professional update to `README.md`. Highlight the newest version baseline and any new SRE guardrails.
3. Generate a high-fidelity system architecture diagram directly in `README.md` using Mermaid Markdown for technical accuracy. Ensure it uses a clean, vibrant theme (like "nano banana" style colors if configured) and contains ZERO typos or garbled text.
4. Use the image generator tool to create a versioned system architecture image (e.g. `docs/assets/system_architecture_v2_7_x.png`) based strictly on the Mermaid diagram logic. When prompting the image generator, YOU MUST USE THE FOLLOWING PRECISE INSTRUCTIONS:
    * **Global Aesthetic & Theming:** Deep dark blue/black background (`#050A1F`) with a subtle low-opacity isometric grid. Strict neon color palette for grouping: Ingress & Persistence = Neon Blue/Cyan, Chat Router = Deep Violet/Purple, Ingestion Engine = Neon Green (Success) & Red (Errors), CQRS = Cyan/Teal. Apply an outer glow (10-15px blur) and solid bright stroke (2-3px) matching the zone color to all containers.
    * **Structural Simplification & Node Design:** Use standardized vector icons (speech bubbles, lightning bolts, databases) placed to the left of concise text labels. Consolidate micro-processes into single conceptual nodes (e.g. merge "Deep Copy", "Grounding", "Sliding Window" into "Message/Context"). Transform fallback cascades into a horizontal sequence of minimal, circular nodes using single-letter identifiers (G, O, N, Gm, Ol).
    * **Routing & Data Flow:** Upgrade primary routing arrows using thick, vibrant gradient strokes (e.g. Ingress Cyan to Router Purple). Increase stroke weight of all connecting arrows. Maintain strict orthogonal routing with rounded corners (8-12px radius) at elbows.
    * **Typography Hierarchy:** Enforce a bold, highly legible sans-serif font (Inter, Montserrat, Roboto). Force internal node text to crisp white (`#FFFFFF`). Keep labels to 1-3 words maximum (e.g. `Schema Extraction`).
    * **Versioning:** Clearly display the current Git submission version as a title/label.
    * After generating, embed the new image at the top of the README architecture section, and wrap the raw Mermaid code block in a `<details><summary>Mermaid Source</summary>...</details>` dropdown. NEVER overwrite the old image file.
5. Show the proposed `README.md` and generated images to the user for approval.
5. Once approved, stage the documentation and architecture asset updates. // turbo
6. Run `git add README.md retrospective.md walkthrough.md docs/assets/system_architecture_v*.png`
7. Commit the documentation and asset updates. // turbo
8. Run `git commit -m "docs: auto-sync showcase documentation, architecture diagram, and logs"`
9. Push to the main branch. // turbo
10. Run `git push origin main`
11. Confirm to the user that the showcase is live on GitHub.