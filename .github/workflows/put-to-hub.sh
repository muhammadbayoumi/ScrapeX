# Put one file into the public delivery endpoint, creating or replacing it.
#
# WHY THIS IS A FILE AND NOT THREE COPIES OF EIGHT LINES. The release publishes
# three things into mbiX-hub — the version manifest, the privacy policy and the
# support page — and the Contents API needs the same awkward two-step for each:
# read the existing blob's sha, then send the content with that sha, or without
# one if the file is not there yet. Three copies is three places for the
# create-versus-replace branch to be got wrong, and the one that is wrong is the
# one that runs a month from now on a file that happens to exist.
#
# WHY NOT `git push`. It would need a clone of the hub, a branch, a committer
# identity and a merge if anything else touched it. This is one HTTP call
# against one path, and it cannot disturb the seventy-six add-in releases living
# in the same repository.
#
# Sourced, not executed: it needs GH_TOKEN and PUBLIC_REPO from the job's env.

put_to_hub() {
  local remote="$1" local_file="$2" message="$3" sha args

  # The API needs the current blob's sha to REPLACE, and rejects one when
  # CREATING. There is no sha the first time, and `|| true` is how the 404 that
  # says so stops being fatal.
  sha=$(gh api "repos/${PUBLIC_REPO}/contents/${remote}" --jq .sha 2>/dev/null || true)

  args=(-X PUT
        -f "message=${message}"
        -f "content=$(base64 -w0 "$local_file")"
        -f "path=${remote}")
  if [ -n "$sha" ]; then
    args+=(-f "sha=$sha")
    echo "replacing ${remote} (${sha})"
  else
    echo "creating ${remote}"
  fi

  gh api "repos/${PUBLIC_REPO}/contents/${remote}" "${args[@]}" --jq .content.path
}
