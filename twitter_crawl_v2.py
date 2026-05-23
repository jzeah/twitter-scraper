#!/usr/bin/env python
"""
Twitter 爬虫命令行工具 v2
"""
import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from twitter_scraper_v2 import TwitterScraper


async def main():
    parser = argparse.ArgumentParser(description='Twitter 爬虫工具')
    parser.add_argument('--username', '-u', type=str, help='Twitter 用户名（不含 @）')
    parser.add_argument('--type', '-t', type=str, 
                       choices=['tweets', 'retweets', 'bookmarks', 'all'],
                       default='all',
                       help='爬取类型')
    parser.add_argument('--max-count', '-m', type=int, default=50,
                       help='最大爬取数量（默认 50）')
    parser.add_argument('--username-login', type=str, help='登录用户名')
    parser.add_argument('--password', type=str, help='登录密码')

    args = parser.parse_args()

    if args.type in ['retweets'] and not args.username:
        print("❌ 需要指定 --username")
        sys.exit(1)

    scraper = TwitterScraper(headless=False, slow_mo=100)

    try:
        await scraper.init_browser()

        cookies_path = "twitter_cookies.json"
        await scraper.login(
            username=args.username_login,
            password=args.password,
            cookies_path=cookies_path
        )

        if not args.username:
            args.username = input("\n请输入 Twitter 用户名（不含 @）: ").strip()

        results = {}

        if args.type in ['tweets', 'all']:
            print("\n" + "="*50)
            print("📝 爬取发帖...")
            print("="*50)
            tweets = await scraper.scrape_profile_tweets(args.username, args.max_count)
            if tweets:
                json_path = await scraper.save_to_json(tweets, f"{args.username}_tweets.json")
                csv_path = await scraper.save_to_csv(tweets, f"{args.username}_tweets.csv")
                results['tweets'] = {'count': len(tweets), 'json': json_path, 'csv': csv_path}

        if args.type in ['retweets', 'all']:
            print("\n" + "="*50)
            print("🔄 爬取转推...")
            print("="*50)
            retweets = await scraper.scrape_retweets(args.username, args.max_count)
            if retweets:
                json_path = await scraper.save_to_json(retweets, f"{args.username}_retweets.json")
                results['retweets'] = {'count': len(retweets), 'json': json_path}

        if args.type in ['bookmarks', 'all']:
            if scraper.is_logged_in:
                print("\n" + "="*50)
                print("⭐ 爬取书签...")
                print("="*50)
                bookmarks = await scraper.scrape_bookmarks(args.max_count)
                if bookmarks:
                    json_path = await scraper.save_to_json(bookmarks, "bookmarks.json")
                    csv_path = await scraper.save_to_csv(bookmarks, "bookmarks.csv")
                    results['bookmarks'] = {'count': len(bookmarks), 'json': json_path, 'csv': csv_path}

        print("\n" + "="*50)
        print("🎉 爬取完成！")
        print("="*50)
        for key, value in results.items():
            print(f"  {key}: {value['count']} 条")

    except KeyboardInterrupt:
        print("\n⚠️ 已取消")
    except Exception as e:
        print(f"\n❌ 错误: {e}")
        import traceback
        traceback.print_exc()
    finally:
        input("\n按 Enter 关闭浏览器...")
        await scraper.close()


if __name__ == "__main__":
    asyncio.run(main())
