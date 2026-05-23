#!/usr/bin/env python3
"""
GitHub 上传脚本（简化版）
"""
import base64
import json
import sys
import urllib.request
import urllib.error

TOKEN = "YOUR_TOKEN_HERE"  # <-- 填入你的 GitHub Token
REPO = "jzeah/twitter-scraper"  # 仓库地址

def upload(filepath):
    filename = filepath.split("/")[-1]
    api_url = f"https://api.github.com/repos/{REPO}/contents/{filename}"
    
    print(f"上传: {filepath}")
    print(f"目标: {api_url}")
    
    try:
        with open(filepath, "rb") as f:
            content = base64.b64encode(f.read()).decode()
        
        # 检查是否已存在
        sha = None
        try:
            req = urllib.request.Request(api_url, headers={"Authorization": f"token {TOKEN}"})
            with urllib.request.urlopen(req) as resp:
                sha = json.loads(resp.read()).get("sha")
                print("📝 文件存在，将更新")
        except urllib.error.HTTPError:
            print("✨ 新文件")
        
        # 上传
        payload = {"message": f"Upload {filename}", "content": content}
        if sha:
            payload["sha"] = sha
        
        data = json.dumps(payload).encode()
        req = urllib.request.Request(api_url, data=data, headers={
            "Authorization": f"token {TOKEN}",
            "Content-Type": "application/json"
        })
        
        with urllib.request.urlopen(req) as resp:
            result = json.loads(resp.read())
            url = result["content"]["html_url"]
            print(f"✅ 成功: {url}")
            return url
            
    except urllib.error.HTTPError as e:
        print(f"❌ HTTP错误 {e.code}: {e.reason}")
        print(e.read().decode())
    except Exception as e:
        print(f"❌ 错误: {e}")
    
    return None

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python upload.py <文件路径>")
        sys.exit(1)
    
    if TOKEN == "YOUR_TOKEN_HERE":
        print("❌ 请先编辑脚本，填入 TOKEN")
        sys.exit(1)
    
    upload(sys.argv[1])
