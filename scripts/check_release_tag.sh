#!/usr/bin/env bash
# Usage: check_release_tag.sh TAG COMMIT
# Fails unless no release uses TAG and TAG is either unused or already points to
# COMMIT. gh release create ignores --target when the tag exists, so a tag that
# points elsewhere would publish the installers under the wrong commit.
set -euo pipefail

tag="$1"
commit="$2"

if gh release view "$tag" >/dev/null 2>&1; then
  echo "::error::Release $tag already exists."
  exit 1
fi

status=0
git ls-remote --exit-code --tags origin "refs/tags/$tag" >/dev/null || status=$?
if [[ $status -eq 2 ]]; then
  exit 0
elif [[ $status -ne 0 ]]; then
  echo "::error::Could not check whether tag $tag exists."
  exit "$status"
fi

git fetch --no-tags origin "refs/tags/$tag:refs/tags/$tag"
tag_commit="$(git rev-parse "refs/tags/$tag^{commit}")"
if [[ "$tag_commit" != "$commit" ]]; then
  echo "::error::Tag $tag points to $tag_commit, not the release commit $commit."
  exit 1
fi
