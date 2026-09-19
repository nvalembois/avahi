#!/usr/bin/env python3
import os
import requests
from datetime import datetime, timedelta, UTC
import sys

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
if not GITHUB_TOKEN:
    print("❌ GITHUB_TOKEN not set")
    sys.exit(1)
GITHUB_REPOSITORY = os.getenv("GITHUB_REPOSITORY")
if not GITHUB_REPOSITORY:
    print("❌ GITHUB_REPOSITORY not set")
    sys.exit(1)
PACKAGE_NAME = GITHUB_REPOSITORY.split("/")[-1]
THRESHOLD_DAYS = int(os.getenv("THRESHOLD_DAYS", "30"))
DRY_RUN = os.getenv("DRY_RUN", "").lower() in ["1", "true", "yes", "y"]
GITHUB_HEADERS = {
    "Accept": "application/vnd.github.v3+json",
    "Authorization": f"token {GITHUB_TOKEN}",
}

print(f"🔍 Fetching container images for {GITHUB_REPOSITORY}")
print(f"📅 Threshold: {THRESHOLD_DAYS} days")

now = datetime.now(UTC)
deleted_count = 0
kept_count = 0
used_layers = []
unused_layers = []

def get_ghcr_token():
    r = requests.get(
        "https://ghcr.io/token",
        params={"scope": f"repository:{GITHUB_REPOSITORY}:pull"},
        headers={"Authorization": f"Bearer {GITHUB_TOKEN}"},
    )
    r.raise_for_status()
    return r.json()["token"]

# ── 2. Récupérer le manifest d'un digest ─────────────────────────────────────

def get_manifest(digest, registry_token):
    r = requests.get(
        f"https://ghcr.io/v2/{GITHUB_REPOSITORY}/manifests/{digest}",
        headers={
            "Authorization": f"Bearer {registry_token}",
            "Accept": ", ".join([
                "application/vnd.oci.image.index.v1+json",
                "application/vnd.docker.distribution.manifest.list.v2+json",
                "application/vnd.oci.image.manifest.v1+json",
                "application/vnd.docker.distribution.manifest.v2+json",
            ]),
        },
    )
    r.raise_for_status()
    return r.json()

def all_versions():
    page = 1
    while True:
        r = requests.get(
            f"https://api.github.com/user/packages/container/{PACKAGE_NAME}/versions",
            headers=GITHUB_HEADERS,
            params={"per_page": 50, "page": page},
        )
        r.raise_for_status()
        batch = r.json()
        if not batch:
            return
        for version in batch:
            yield from [
                {
                     "id": version.get("id", ""),
                     "digest": version.get("name", "unknown"),
                     "tags": version.get("metadata", {}).get("container", {}).get("tags", []),
                     "updated_at": version.get("updated_at", ""),
                }
            ]
        page += 1

GHCR_TOKEN = get_ghcr_token()

keep_versions = {}
delete_versions = {}
keeped_layers = {}

for version in all_versions():
    if len(version["tags"]) == 0:
        delete_versions[version["digest"]] = version
        continue

    if "latest" in version["tags"]:
        keep_versions[version["digest"]] = version
        continue

    try:
        updated_at = datetime.fromisoformat(version["updated_at"])
    except Exception as e:
        print(f"❌ Error processing version: {e}")
        sys.exit(1)
        
    age_days = (now - updated_at).days

    if age_days > THRESHOLD_DAYS:
        delete_versions[version["digest"]] = version
        continue

    keep_versions[version["digest"]] = version

# Pour chaque version taggée, récupérer les digests enfants
for digest in keep_versions:
    try:
        manifest = get_manifest(digest, GHCR_TOKEN)

        # Manifest list (multi-arch) → collecter les enfants
        if "manifests" in manifest:
            for child in manifest["manifests"]:
                child_digest = child["digest"]
                if child_digest in delete_versions:
                    keeped_layers[child_digest] = delete_versions[child_digest]
                    del delete_versions[child_digest]
                    print(f"  ↳ référencé : {child_digest[:19]} ({child.get('platform', {}).get('os', '?')}/{child.get('platform', {}).get('architecture', '?')})")
                else:
                    print(f"  ⚠️ non référencé : {child_digest[:19]} ({child.get('platform', {}).get('os', '?')}/{child.get('platform', {}).get('architecture', '?')})")
                    

    except Exception as e:
        print(f"⚠️  Impossible de lire le manifest {digest[:19]}: {e}")
        sys.exit(1)


print(f"\n{'='*60}")

for (digest, version) in keep_versions.items():
    print(f"✅ Keeping: {digest},{version["tags"]} (updated at {version["updated_at"]})")
for (digest, version) in keeped_layers.items():
    print(f"✅ Keeping layer: {digest} (updated at {version["updated_at"]})")
for (digest, version) in delete_versions.items():
    if "" == version["id"]:
        print(f"   ❌ No id for {digest},{version["tags"]} (updated at {version["updated_at"]}")
        continue

    if DRY_RUN:
        print(f"🗑️  Would delete (DRY_RUN): {digest},{version["tags"]} (updated at {version["updated_at"]})")
        continue

    print(f"🗑️  Deleting: {digest},{version["tags"]} (updated at {version["updated_at"]})")
    
    delete_url = f"https://api.github.com/user/packages/container/{PACKAGE_NAME}/versions/{version["id"]}"
    delete_response = requests.delete(delete_url, headers=GITHUB_HEADERS)
    
    if delete_response.status_code not in [200, 204]:
        print(f"   ❌ Error: {delete_response.status_code} - {delete_response.text}")
        continue

    print("   ✅ Successfully deleted")

print(f"\n{'='*60}")
deleted_count = len(delete_versions)
kept_tags = len(keep_versions)
kept_layers = len(keep_versions)
print(f"📊 Summary: {deleted_count} deleted, {kept_tags} kept images, {kept_tags} kept layers")
print(f"{'='*60}")
