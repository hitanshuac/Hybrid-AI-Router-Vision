---
description: 
---

---
description: Automatically synthesize project logs and push updated documentation to GitHub.
---

# Publish Showcase Workflow

1. Read the current contents of `retrospective.md`, `walkthrough.md`, and `implementation_plan.md`.
2. Synthesize these files to write a comprehensive, professional update to `README.md`. Highlight the newest version baseline and any new SRE guardrails.
3. Generate a high-fidelity system architecture diagram (`docs/assets/system_architecture.png`) reflecting the new version's layout (Polymorphic Ingestion Engine + Vision Cascade) using the AI image generator tool, ensuring it looks visually premium.
4. Show the proposed `README.md` and generated architecture to the user for approval.
5. Once approved, stage the documentation and architecture asset updates. // turbo
6. Run `git add README.md retrospective.md walkthrough.md docs/assets/system_architecture.png`
7. Commit the documentation and asset updates. // turbo
8. Run `git commit -m "docs: auto-sync showcase documentation, architecture diagram, and logs"`
9. Push to the main branch. // turbo
10. Run `git push origin main`
11. Confirm to the user that the showcase is live on GitHub.