import os
import base64
import requests

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_REPO = os.getenv("GITHUB_REPO")

def commit_to_github(file_path, commit_message):
    if not GITHUB_TOKEN or not GITHUB_REPO:
        print("❌ GITHUB_TOKEN эсвэл GITHUB_REPO олдсонгүй.")
        return

    try:
        with open(file_path, "rb") as f:
            content = f.read()
        b64_content = base64.b64encode(content).decode("utf-8")
        api_url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{file_path}"

        # get sha
        res = requests.get(api_url, headers={"Authorization": f"Bearer {GITHUB_TOKEN}"})
        sha = res.json().get("sha")

        data = {
            "message": commit_message,
            "content": b64_content,
            "sha": sha
        }

        res = requests.put(
            api_url,
            headers={
                "Authorization": f"Bearer {GITHUB_TOKEN}",
                "Content-Type": "application/json"
            },
            json=data
        )

        if not res.ok:
            print(f"❌ GitHub branch update алдаа: {res.status_code} {res.text}")
            return

        print(f"✅ {file_path} файлыг GitHub руу амжилттай commit хийлээ.")
    except Exception as e:
        print("❌ commit_to_github алдаа:", e)
