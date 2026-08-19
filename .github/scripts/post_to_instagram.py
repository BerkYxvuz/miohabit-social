"""
Reads image.png + caption.txt from social/pending/, publishes them to Instagram
via the Instagram Graph API (Content Publishing), then moves the files into
social/history/<date>.png and social/history/<date>.txt so the same content
is never reused.

Required environment variables (set as GitHub Secrets):
  IG_ACCESS_TOKEN   - long-lived Page/Instagram access token with
                      instagram_content_publish, instagram_basic, pages_show_list,
                      pages_read_engagement, business_management
  IG_BUSINESS_ID    - Instagram Business Account ID (numeric)

Provided automatically by GitHub Actions:
  GITHUB_REPOSITORY - "owner/repo"
  GITHUB_REF_NAME    - branch name (e.g. "main")

Note: this script expects the repo to be PUBLIC, since Instagram's servers
fetch the image from a public raw.githubusercontent.com URL. If the repo is
private, replace `image_url` below with a URL from an image host instead.
"""

import os
import sys
import time
import shutil

import requests

GRAPH_API_VERSION = "v20.0"
PENDING_DIR = "social/pending"
HISTORY_DIR = "social/history"


def main():
    ig_token = os.environ["IG_ACCESS_TOKEN"]
    ig_business_id = os.environ["IG_BUSINESS_ID"]
    repo = os.environ["GITHUB_REPOSITORY"]
    ref_name = os.environ.get("GITHUB_REF_NAME", "main")

    caption_path = os.path.join(PENDING_DIR, "caption.txt")
    image_path = os.path.join(PENDING_DIR, "image.png")

    if not os.path.exists(caption_path) or not os.path.exists(image_path):
        print("No pending post found (missing image.png or caption.txt). Nothing to do.")
        sys.exit(0)

    with open(caption_path, "r", encoding="utf-8") as f:
        caption = f.read().strip()

    image_url = f"https://raw.githubusercontent.com/{repo}/{ref_name}/{image_path}"
    print(f"Using image URL: {image_url}")

    create_resp = requests.post(
        f"https://graph.facebook.com/{GRAPH_API_VERSION}/{ig_business_id}/media",
        data={
            "image_url": image_url,
            "caption": caption,
            "access_token": ig_token,
        },
        timeout=30,
    )
    create_resp.raise_for_status()
    creation_id = create_resp.json()["id"]
    print(f"Created media container: {creation_id}")

    status = None
    for attempt in range(12):
        time.sleep(5)
        status_resp = requests.get(
            f"https://graph.facebook.com/{GRAPH_API_VERSION}/{creation_id}",
            params={"fields": "status_code", "access_token": ig_token},
            timeout=30,
        )
        status_resp.raise_for_status()
        status = status_resp.json().get("status_code")
        print(f"Attempt {attempt + 1}: status={status}")
        if status == "FINISHED":
            break
        if status == "ERROR":
            raise RuntimeError("Instagram reported an error processing the media container.")
    else:
        raise TimeoutError(f"Media container never reached FINISHED status (last: {status}).")

    publish_resp = requests.post(
        f"https://graph.facebook.com/{GRAPH_API_VERSION}/{ig_business_id}/media_publish",
        data={"creation_id": creation_id, "access_token": ig_token},
        timeout=30,
    )
    publish_resp.raise_for_status()
    print("Published:", publish_resp.json())

    os.makedirs(HISTORY_DIR, exist_ok=True)
    today = time.strftime("%Y-%m-%d")
    shutil.move(image_path, os.path.join(HISTORY_DIR, f"{today}.png"))
    shutil.move(caption_path, os.path.join(HISTORY_DIR, f"{today}.txt"))
    print(f"Moved published post into {HISTORY_DIR}/{today}.*")


if __name__ == "__main__":
    main()
