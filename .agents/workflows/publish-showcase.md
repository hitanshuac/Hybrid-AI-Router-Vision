---
description: 
---

---
description: Automatically synthesize project logs and push updated documentation to GitHub.
---

# Publish Showcase Workflow

1. Read the current contents of `retrospective.md`, `walkthrough.md`, and `implementation_plan.md`.
2. Synthesize these files to write a comprehensive, professional update to `README.md`. Highlight the newest version baseline and any new SRE guardrails.
3. Generate a high-fidelity system architecture diagram directly in `README.md` using Mermaid Markdown for technical accuracy.
4. Additionally, use the AI image generator to create a visually attractive, compact, and simplified "human-readable" version of the architecture diagram for non-technical stakeholders (avoiding overly complex jargon). Save it as a NEW file named with the current version (e.g. `docs/assets/system_architecture_v2_7_1.png`), NEVER overwriting the old file. Embed this new image at the top of the README architecture section.
5. Show the proposed `README.md` and generated images to the user for approval.
5. Once approved, stage the documentation and architecture asset updates. // turbo
6. Run `git add README.md retrospective.md walkthrough.md docs/assets/system_architecture_v*.png`
7. Commit the documentation and asset updates. // turbo
8. Run `git commit -m "docs: auto-sync showcase documentation, architecture diagram, and logs"`
9. Push to the main branch. // turbo
10. Run `git push origin main`
11. Confirm to the user that the showcase is live on GitHub.