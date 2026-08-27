#!/usr/bin/env bash

set -euo pipefail

readonly template_path=".github/pull_request_template.md"
readonly caller_path=".github/workflows/pr-check.yml"
readonly sync_branch="automation/sync-pr-template"
readonly commit_message="chore(pr): 同步组织 PR 模板"
readonly pull_title="chore(pr): 同步组织 PR 模板"

: "${GH_TOKEN:?缺少 ITSO_AUTOMATION_TOKEN}"
: "${OWNER:?缺少组织名}"
: "${SOURCE_REPOSITORY:?缺少源仓库名}"
: "${SOURCE_SHA:?缺少源提交 SHA}"

dry_run="${DRY_RUN:-false}"
if [[ "${dry_run}" != "true" && "${dry_run}" != "false" ]]; then
  echo "::error::DRY_RUN 只能是 true 或 false。"
  exit 1
fi

if [[ ! -f "${template_path}" ]]; then
  echo "::error::找不到组织 PR 模板：${template_path}"
  exit 1
fi

template_base64="$(base64 < "${template_path}" | tr -d '\n')"
search_query="org:${OWNER} \"${OWNER}/.github/.github/workflows/pr-check.yml@main\""

declare -a repositories=()
while IFS= read -r repository; do
  [[ -n "${repository}" ]] && repositories+=("${repository}")
done < <(
  gh api --method GET /search/code \
    -f q="${search_query}" \
    -f per_page=100 \
    --paginate \
    --jq '.items[].repository.full_name' |
    sort -u
)

if ((${#repositories[@]} == 0)); then
  echo "::error::未找到调用公共 PR 规范检查的仓库，停止同步。"
  exit 1
fi

results_file="$(mktemp)"
trap 'rm -f "${results_file}"' EXIT
failed=0

record_result() {
  local repository="$1"
  local result="$2"
  local detail="$3"
  jq -nc \
    --arg repository "${repository}" \
    --arg result "${result}" \
    --arg detail "${detail}" \
    '[$repository, $result, $detail]' >> "${results_file}"
}

select_merge_method() {
  local repository="$1"
  local settings
  settings="$(gh api "repos/${repository}" \
    --jq '[.allow_squash_merge, .allow_merge_commit, .allow_rebase_merge] | @tsv')"

  case "${settings}" in
    true$'\t'* ) printf '%s\n' squash ;;
    false$'\t'true$'\t'* ) printf '%s\n' merge ;;
    false$'\t'false$'\t'true ) printf '%s\n' rebase ;;
    * ) return 1 ;;
  esac
}

for repository in "${repositories[@]}"; do
  if [[ "${repository}" == "${SOURCE_REPOSITORY}" ]]; then
    continue
  fi

  repo_info="$(gh api "repos/${repository}" --jq '{archived, fork, default_branch}')"
  if [[ "$(jq -r '.archived or .fork' <<< "${repo_info}")" == "true" ]]; then
    record_result "${repository}" "跳过" "仓库已归档或是 fork"
    continue
  fi
  default_branch="$(jq -r '.default_branch' <<< "${repo_info}")"

  if ! caller="$(gh api --method GET "repos/${repository}/contents/${caller_path}" \
    -f ref="${default_branch}" \
    -H 'Accept: application/vnd.github.raw+json' 2>/dev/null)"; then
    caller=""
  fi
  if ! grep -Fq "uses: ${OWNER}/.github/.github/workflows/pr-check.yml@main" <<< "${caller}"; then
    record_result "${repository}" "跳过" "代码搜索结果不再调用公共 PR 检查"
    continue
  fi

  if target_file="$(gh api --method GET "repos/${repository}/contents/${template_path}" \
    -f ref="${default_branch}" 2>/dev/null)"; then
    target_content="$(jq -r '.content' <<< "${target_file}" | tr -d '\n')"
  else
    target_content=""
  fi
  if [[ -n "${target_content}" && "${target_content}" == "${template_base64}" ]]; then
    record_result "${repository}" "无需同步" "模板已是最新版本"
    continue
  fi

  if [[ "${dry_run}" == "true" ]]; then
    record_result "${repository}" "需要同步" "dry-run 未修改仓库"
    continue
  fi

  echo "同步 ${repository} 的 PR 模板。"
  base_sha="$(gh api "repos/${repository}/git/ref/heads/${default_branch}" --jq '.object.sha')"
  encoded_sync_branch="$(jq -rn --arg value "${sync_branch}" '$value | @uri')"
  if ref_response="$(gh api "repos/${repository}/git/ref/heads/${encoded_sync_branch}" 2>/dev/null)"; then
    existing_ref="$(jq -r '.object.sha' <<< "${ref_response}")"
  else
    existing_ref=""
  fi

  if [[ -n "${existing_ref}" ]]; then
    gh api --method PATCH "repos/${repository}/git/refs/heads/${encoded_sync_branch}" \
      -F sha="${base_sha}" \
      -F force=true >/dev/null
  else
    gh api --method POST "repos/${repository}/git/refs" \
      -f ref="refs/heads/${sync_branch}" \
      -f sha="${base_sha}" >/dev/null
  fi

  if target_file="$(gh api --method GET "repos/${repository}/contents/${template_path}" \
    -f ref="${sync_branch}" 2>/dev/null)"; then
    target_sha="$(jq -r '.sha' <<< "${target_file}")"
  else
    target_sha=""
  fi
  content_args=(
    --method PUT
    "repos/${repository}/contents/${template_path}"
    -f message="${commit_message}"
    -f content="${template_base64}"
    -f branch="${sync_branch}"
  )
  if [[ -n "${target_sha}" ]]; then
    content_args+=(-f sha="${target_sha}")
  fi
  sync_head="$(gh api "${content_args[@]}" --jq '.commit.sha')"

  pull_number="$(gh api --method GET "repos/${repository}/pulls" \
    -f state=open \
    -f head="${OWNER}:${sync_branch}" \
    -f base="${default_branch}" \
    --jq '.[0].number // empty')"
  if [[ -z "${pull_number}" ]]; then
    pull_body="$(cat <<EOF
## 背景

组织 PR 模板已更新，需要同步到调用公共 PR 规范检查的仓库。

## 改动

同步 \`${template_path}\`，来源为 \`${SOURCE_REPOSITORY}@${SOURCE_SHA}\`。

## 影响

仅影响后续新建 PR 时预填的描述模板，不修改业务代码或现有 PR。

## 验证

同步流程已对比源、目标模板内容，并确认目标仓库仍调用公共 PR 规范检查。

## 材料

由组织 PR 模板同步自动化账号创建并合并。
EOF
)"
    pull_number="$(gh api --method POST "repos/${repository}/pulls" \
      -f title="${pull_title}" \
      -f head="${sync_branch}" \
      -f base="${default_branch}" \
      -f body="${pull_body}" \
      --jq '.number')"
  fi

  merge_method="$(select_merge_method "${repository}")" || {
    record_result "${repository}" "失败" "仓库未启用任何 PR 合并方式，PR #${pull_number} 已保留"
    failed=1
    continue
  }

  if gh pr merge "${pull_number}" \
    --repo "${repository}" \
    --admin \
    --match-head-commit "${sync_head}" \
    "--${merge_method}"; then
    record_result "${repository}" "已合并" "PR #${pull_number}（${merge_method}）"
  else
    record_result "${repository}" "失败" "PR #${pull_number} 未合并；请检查自动化令牌的管理员权限"
    failed=1
  fi
done

{
  echo "## 组织 PR 模板同步结果"
  echo
  echo "源提交：\`${SOURCE_SHA}\`"
  echo
  echo '| 仓库 | 结果 | 说明 |'
  echo '| --- | --- | --- |'
  while IFS= read -r item; do
    repository="$(jq -r '.[0]' <<< "${item}")"
    result="$(jq -r '.[1]' <<< "${item}")"
    detail="$(jq -r '.[2]' <<< "${item}")"
    echo "| \`${repository}\` | ${result} | ${detail} |"
  done < "${results_file}"
} >> "${GITHUB_STEP_SUMMARY:-/dev/stdout}"

exit "${failed}"
