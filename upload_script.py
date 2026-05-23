#!/usr/bin/env python
"""
GitHub 文件上传工具
使用方法:
    python upload_script.py <文件路径>
    python upload_script.py report.pdf

上传前请在下方填入你的 GitHub Token
"""
import base64
import json
import os
import sys
import urllib.request

# ==================== 请在这里填入你的信息 ====================
TOKEN = ""  # 填入你的 GitHub Token
REPO = "jzeah/twitter-scraper"  # 仓库地址
# ==================== 请在这里填入你的信息 ====================

def upload_file(filepath):
    """上传文件到 GitHub"""
    if not TOKEN:
        print("❌ 请先在脚本中填入 TOKEN")
        return None
    
    if not os.path.exists(filepath):
        print(f"❌ 文件不存在: {filepath}")
        return None
    
    filename = os.path.basename(filepath)
    api_url = f"https://api.github.com/repos/{REPO}/contents/{filename}"
    
    print(f"📤 上传: {filepath}")
    print(f"📍 目标: {api_url}")
    
    try:
        with open(filepath, 'rb') as f:
            content = base64.b64encode(f.read()).decode()
        
        # 检查是否已存在
        req = urllib.request.Request(api_url, headers={
            'Authorization': f'token {TOKEN}',
            'Accept': 'application/vnd.github.v3+json'
        })
        
        sha = None
        try:
            with urllib.request.urlopen(req) as resp:
                sha = json.loads(resp.read()).get('sha')
                print("📝 文件已存在，将更新")
        except:
            print("✨ 新文件，将创建")
        
        data = json.dumps({
            'message': f'Upload {filename}',
            'content': content
        }).encode()
        
        if sha:
            data = json.dumps({
                'message': f'Update {filename}',
                'content': content,
                'sha': sha
            }).encode()
        
        req = urllib.request.Request(api_url, data=data, headers={
            'Authorization': f'token {TOKEN}',
            'Content-Type': 'application/json'
        })
        
        with urllib.request.urlopen(req) as resp:
            result = json.loads(resp.read())
            url = result.get('content', {}).get('html_url', '')
            print(f"✅ 成功: {url}")
            return url
    
    except Exception as e:
        print(f"❌ 失败: {e}")
    return None


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python upload_script.py <文件路径>")
        print("示例: python upload_script.py report.pdf")
        print("示例: python upload_script.py data.json")
        sys.exit(1)
    
    upload_file(sys.argv[1])
