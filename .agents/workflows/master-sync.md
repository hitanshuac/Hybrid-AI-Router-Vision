---
description: A master orchestration workflow that sequentially updates documentation, publishes the showcase, and secures a Git checkpoint.
---

# Master Sync Workflow

1. Invoke the **Update Docs Workflow** to ensure all `.md` files are strictly synced with the latest Python and SQL codebase.
2. Invoke the **Publish Showcase Workflow** to generate the final Mermaid architecture diagram and prepare the `README.md` for the showcase.
3. Invoke the **Secure Checkpoint Workflow** to securely commit and push the updated codebase and all newly generated documentation to GitHub in one seamless action.
