#!/usr/bin/env bash
set -euo pipefail

PROFILE="${1:-local}"

copy_if_missing() {
  local source_file="$1"
  local target_file="$2"

  if [ -f "$target_file" ]; then
    echo "Keeping existing $target_file"
    return
  fi

  cp "$source_file" "$target_file"
  echo "Created $target_file from $source_file"
}

copy_profile_if_missing() {
  local local_source="$1"
  local staging_source="$2"
  local target_file="$3"

  if [ -f "$target_file" ]; then
    echo "Keeping existing $target_file"
    return
  fi

  local source_file="$local_source"
  if [ "$PROFILE" = "staging" ]; then
    source_file="$staging_source"
  fi

  cp "$source_file" "$target_file"
  echo "Created $target_file from $source_file"
}

copy_profile_if_missing "backend/.env.example" "backend/.env.staging.example" "backend/.env"
copy_if_missing "backend/.env.staging.example" "backend/.env.staging"
copy_profile_if_missing "frontend/.env.local.example" "frontend/.env.staging.local.example" "frontend/.env.local"
copy_if_missing "frontend/.env.staging.local.example" "frontend/.env.staging.local"
copy_profile_if_missing "mobile/.env.example" "mobile/.env.staging.example" "mobile/.env"
copy_if_missing "mobile/.env.staging.example" "mobile/.env.staging"
