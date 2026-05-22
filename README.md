# Twitter 爬虫工具 🐦

一个简单的 Twitter 爬虫工具，支持爬取发帖、转推和书签。

## 功能

- 📝 爬取用户发帖
- 🔄 爬取用户转推
- ⭐ 爬取书签（需要登录）
- 🛡️ 防封策略（模拟人类浏览速度）
- 💾 JSON/CSV 格式导出

## 安装

```bash
# 安装依赖
pip install uv
uv sync
uv run playwright install chromium
```

## 使用

```bash
# 爬取用户发帖
python twitter_crawl.py -u username -t tweets

# 爬取转推
python twitter_crawl.py -u username -t retweets

# 爬取书签（需要扫码登录）
python twitter_crawl.py -t bookmarks
```

## 参数说明

| 参数 | 说明 |
|------|------|
| `-u, --username` | Twitter 用户名（不含 @） |
| `-t, --type` | 爬取类型：tweets/retweets/bookmarks/all |
| `-m, --max-count` | 最大爬取数量（默认 100） |

## 注意事项

⚠️ 请确保用途合规，不要高频爬取
