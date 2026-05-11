---
description: description: Automatically commit and push the current workspace state to GitHub to prevent data loss.
---

description: Automatically commit and push the current workspace state to GitHub to prevent data loss.

# Secure Checkpoint Workflow

1. Ask the user for a brief commit message describing the current state.
2. Stage all current files, including hidden and newly recovered files. // turbo
3. Run `git add .`
4. Commit the changes safely to the Git ledger. // turbo
5. Run `git commit -m "[Safe Checkpoint] "` appended with the user's message.
6. Push the changes to the remote GitHub repository. // turbo
7. Run `git push origin main`
8. Confirm to the user that their files are permanently secured on GitHub.