# Contributing

1. Propose changes through an issue or pull request.
2. Keep the public code independent of private XOps installations, data, and credentials.
3. Add regression tests for changes to validation, deduplication, and review transitions.
4. Run `python -m unittest discover -s tests -v` with Python 3.11 or later.
5. Never include real PUBLIC_POSTS_V1 user content as fixtures: use synthetic examples only.
