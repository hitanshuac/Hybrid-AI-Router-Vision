---
description: 
---

---
description: Automatically synthesize project logs and push updated documentation to GitHub.
---

# Publish Showcase Workflow

1. Read the current contents of `retrospective.md`, `walkthrough.md`, and `implementation_plan.md`.
2. Synthesize these files to write a comprehensive, professional update to `README.md`. Highlight the newest version baseline and any new SRE guardrails.
3. Show the proposed `README.md` to the user for approval.
4. Once approved, stage the documentation updates. // turbo
5. Run `git add README.md retrospective.md walkthrough.md`
6. Commit the documentation update. // turbo
7. Run `git commit -m "docs: auto-sync showcase documentation and logs"`
8. Push to the main branch. // turbo
9. Run `git push origin main`
10. Confirm to the user that the showcase is live on GitHub.