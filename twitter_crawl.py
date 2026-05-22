#!/usr/bin/env python
"""
Twitter 爬虫命令行工具
使用方法:
    python scripts/twitter_crawl.py --username elonmusk --type tweets
    python scripts/twitter_crawl.py --username elonmusk --type retweets
    python scripts/twitter_crawl.py --type bookmarks
"""
import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.tools.twitter_scraper import TwitterScraper


async def main():
    parser = argparse.ArgumentParser(description='Twitter 爬虫工具')
    parser.add_argument('--username', '-u', type=str, help='Twitter 用户名（不含 @）')
    parser.add_argument('--type', '-t', type=str, 
                       choices=['tweets', 'retweets', 'bookmarks', 'all'],
                       default='all',
                       help='爬取类型: tweets(发帖), retweets(转推), bookmarks(书签), all(全部)')
    parser.add_argument('--max-count', '-m', type=int, default=100,
                       help='最大爬取数量（默认 100）')
    parser.add_argument('--headless', action='store_true',
                       help='无头模式（不显示浏览器窗口）')
    parser.add_argument('--username-login', type=str, help='登录用户名/邮箱/手机号')
    parser.add_argument('--password', type=str, help='登录密码')
    parser.add_argument('--no-save-cookies', action='store_true',
                       help='不保存登录 cookies')
    
    args = parser.parse_args()
    
    # 验证参数
    if args.type in ['retweets'] and not args.username:
        print("❌ 爬取转推需要指定 --username")
        sys.exit(1)
    
    if args.type == 'bookmarks' and not args.username_login:
        print("⚠️  书签功能需要登录，请提供 --username-login 和 --password")
    
    # 创建爬虫实例
    scraper = TwitterScraper(
        headless=args.headless or False,
        slow_mo=100
    )
    
    try:
        # 初始化浏览器
        await scraper.init_browser()
        
        # 登录
        cookies_path = None if args.no_save_cookies else "assets/twitter_cookies.json"
        await scraper.login(
            username=args.username_login,
            password=args.password,
            cookies_path=cookies_path
        )
        
        if not args.username and args.type != 'bookmarks':
            args.username = input("\n请输入要爬取的 Twitter 用户名（不含 @）: ").strip()
        
        results = {}
        
        # 爬取发帖
        if args.type in ['tweets', 'all']:
            print("\n" + "="*50)
            print("📝 开始爬取发帖...")
            print("="*50)
            tweets = await scraper.scrape_profile_tweets(args.username, args.max_count)
            if tweets:
                json_path = await scraper.save_to_json(tweets, f"{args.username}_tweets.json")
                csv_path = await scraper.save_to_csv(tweets, f"{args.username}_tweets.csv")
                results['tweets'] = {'count': len(tweets), 'json': json_path, 'csv': csv_path}
        
        # 爬取转推
        if args.type in ['retweets', 'all']:
            print("\n" + "="*50)
            print("🔄 开始爬取转推...")
            print("="*50)
            retweets = await scraper.scrape_retweets(args.username, args.max_count)
            if retweets:
                json_path = await scraper.save_to_json(retweets, f"{args.username}_retweets.json")
                results['retweets'] = {'count': len(retweets), 'json': json_path}
        
        # 爬取书签
        if args.type in ['bookmarks', 'all']:
            if not scraper.is_logged_in:
                print("⚠️  书签功能需要登录，跳过...")
            else:
                print("\n" + "="*50)
                print("⭐ 开始爬取书签...")
                print("="*50)
                bookmarks = await scraper.scrape_bookmarks(args.max_count)
                if bookmarks:
                    json_path = await scraper.save_to_json(bookmarks, "bookmarks.json")
                    csv_path = await scraper.save_to_csv(bookmarks, "bookmarks.csv")
                    results['bookmarks'] = {'count': len(bookmarks), 'json': json_path, 'csv': csv_path}
        
        # 输出总结
        print("\n" + "="*50)
        print("🎉 爬取完成！")
        print("="*50)
        print("\n📊 爬取结果:")
        for key, value in results.items():
            print(f"  {key}: {value['count']} 条")
            if 'json' in value:
                print(f"    - JSON: {value['json']}")
            if 'csv' in value:
                print(f"    - CSV: {value['csv']}")
        
    except KeyboardInterrupt:
        print("\n⚠️  用户中断操作")
    except Exception as e:
        print(f"\n❌ 发生错误: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await scraper.close()


if __name__ == "__main__":
    asyncio.run(main())
