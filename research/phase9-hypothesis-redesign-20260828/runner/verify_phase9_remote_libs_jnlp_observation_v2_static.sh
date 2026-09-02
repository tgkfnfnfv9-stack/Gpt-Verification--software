#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$repo_root"
root='research/phase9-hypothesis-redesign-20260828'
status_before="$(git status --porcelain)"

test "$GITHUB_REPOSITORY" = 'tgkfnfnfv9-stack/Gpt-Verification--software'
test "$GITHUB_EVENT_NAME" = 'workflow_dispatch'
test "$GITHUB_REF" = 'refs/heads/main'
test "$GITHUB_RUN_NUMBER" = '1'
test "$GITHUB_RUN_ATTEMPT" = '1'
test "$(git rev-parse HEAD)" = "$GITHUB_SHA"

gate_sha="$(sha256sum "$root/spec/remote_libs_jnlp_observation_gate_v2.frozen.json" | cut -d' ' -f1)"
allowlist_sha="$(sha256sum "$root/spec/remote_jnlp_observed_url_allowlist.frozen.json" | cut -d' ' -f1)"
source_audit_sha="$(sha256sum "$root/results/remote-jnlp-run-33500446289/REMOTE_JNLP_INDEPENDENT_AUDIT.json" | cut -d' ' -f1)"
test "$gate_sha" = '0782f250c9d79bee70a862f590182c52bf550c6d08464d140d61dab39ab74487'
test "$allowlist_sha" = '926c7fe3f2531e8bba1c43e1faef4efc7f69baca3ac3fff9ed22d36535c1e970'
test "$source_audit_sha" = '802aa78553f7937c191996082e0037250352df6abf4cff8e11de08e511bb6d8d'

PYTHONDONTWRITEBYTECODE=1 python "$root/runner/verify_phase9_remote_libs_jnlp_observation_v2.py" static
PYTHONDONTWRITEBYTECODE=1 python -m unittest "$root/tests/test_phase9_remote_libs_jnlp_observer_v2.py" -v
test "$(git status --porcelain)" = "$status_before"
