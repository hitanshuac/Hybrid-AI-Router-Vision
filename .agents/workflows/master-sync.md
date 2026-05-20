---
description: A master orchestration workflow that sequentially updates documentation, publishes the showcase, and secures a Git checkpoint.
---

# Master Sync Workflow

1. Invoke the **Update Docs Workflow** to ensure all `.md` files are strictly synced with the latest Python and SQL codebase.
2. Invoke the **Publish Showcase Workflow** to generate both the Mermaid technical architecture and a simplified, human-readable AI-generated image (saved as a new versioned file, never overwriting the old one), and prepare the `README.md` for the showcase.
3. Invoke the **Secure Checkpoint Workflow** to securely commit and push the updated codebase, images, and documentation to GitHub.
