"""Single source of truth for the patcher version.

The release workflow checks this against the git tag it is building, so a tag
that disagrees with the code fails the build instead of shipping a binary that
misreports itself.
"""
VERSION = "1.0.2"
