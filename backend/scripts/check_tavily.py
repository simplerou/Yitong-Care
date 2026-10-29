"""Run after filling the local TAVILY_API_KEY; prints no credentials."""
import argparse
from app.services.web.tavily import get_web_search, WebSearchError


def main():
    parser=argparse.ArgumentParser(description='验证 Tavily 搜索及官方网页正文提取')
    parser.add_argument('query',nargs='?',default='杭州市 高龄 困难老年人 补贴制度')
    args=parser.parse_args()
    service=get_web_search()
    if not service.configured:
        print('尚未配置：请在 backend/.env 中填写 TAVILY_API_KEY，然后重新运行。')
        return 1
    try:
        report=service.search_with_diagnostics(args.query)
        sources=report.sources
        diagnostic=report.diagnostics
        print(f'搜索 {diagnostic.search_count} 条 → 官方候选 {diagnostic.official_count} 条 → 取得正文 {diagnostic.body_count} 条 → 保留 {diagnostic.accepted_count} 条')
        for page in diagnostic.pages:
            print(f'{page.outcome}: {page.reason} | {page.title} | {page.url}')
    except WebSearchError as error:
        if error.diagnostics:
            d=error.diagnostics
            print(f'中断阶段：{d.stage}；搜索 {d.search_count} 条；请求正文 {d.extraction_requested} 条；取得正文 {d.body_count} 条')
        print(str(error))
        return 1
    print(f'取得 {len(sources)} 条官方网页正文。')
    for source in sources:
        print(source.title)
        print(source.url)
        print(f'正文字数：{len(source.content)}；发布日期：{source.published_date or "待核实"}')
    if not sources:
        print('本次未取得正文：可更换关键词后重试；搜索摘要不会作为政策依据。')
    return 0 if sources else 1


if __name__=='__main__':
    raise SystemExit(main())
