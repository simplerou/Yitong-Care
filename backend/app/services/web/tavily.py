"""Search + extract official webpages via Tavily. Search snippets are never evidence."""
from datetime import datetime, UTC
from urllib.parse import urlsplit, urlunsplit
import httpx
from app.core.config import get_settings
from dataclasses import dataclass
from app.schemas.chat import WebSource, WebDiagnostics, WebPageDiagnostic, WebSearchAttempt
from app.services.web.query_plan import focus_terms,source_priority,fallback_queries
from app.services.chat.policy_checks import clean_title, relevance_reason


class WebSearchError(Exception):
    def __init__(self, message, diagnostics=None):
        super().__init__(message)
        self.diagnostics = diagnostics


@dataclass
class SearchReport:
    sources: list[WebSource]
    diagnostics: WebDiagnostics


class TavilySearch:
    def __init__(self, settings):
        self.settings = settings

    @property
    def configured(self):
        return bool(self.settings.tavily_api_key.get_secret_value().strip())

    def allowed_url(self, value):
        if not isinstance(value, str): return None
        try:
            url = urlsplit(value)
            host = (url.hostname or '').lower()
            domains = [d.lower().strip().strip('.') for d in self.settings.tavily_include_domains if d.strip().strip('.')]
            if url.scheme not in {'http','https'} or url.username or url.password or url.port not in (None,80,443): return None
            if not any(host == domain or host.endswith('.'+domain) for domain in domains): return None
            return urlunsplit((url.scheme,url.netloc,url.path,url.query,''))
        except ValueError:
            return None

    @staticmethod
    def excerpt(query, content):
        from app.services.chat.policy_checks import TOPICS
        targets=focus_terms(query)
        words = list(dict.fromkeys([w for w in TOPICS if w in query]+targets))
        text = content.strip()
        if not words or len(text) <= 4000: return text[:4000]
        offsets = {0}
        import re
        for word in words:
            for match in list(re.finditer(re.escape(word),text))[:100]:
                offsets.add(max(0,match.start()-600))
        def score(offset):
            window = text[offset:offset+4000]
            return sum((60 if word in targets else 10) + min(window.count(word),3) for word in words if word in window)
        start = max(sorted(offsets),key=score)
        return text[start:start+4000]

    def search(self, query: str) -> list[WebSource]:
        return self.search_with_diagnostics(query).sources

    def search_with_diagnostics(self, query: str, *, bypass_cache=False) -> SearchReport:
        import hashlib
        import json
        import re
        from app.services.web.cache import search_cache
        ttl = self.settings.tavily_cache_ttl_seconds
        freshness = bypass_cache or bool(re.search(r'最新|现行|当前|有效|废止|目前|现在|今天|更新|调整|20\d{2}', query))
        key = hashlib.sha256(json.dumps([query, self.settings.tavily_include_domains,
            self.settings.tavily_max_results, self.settings.tavily_api_key.get_secret_value(), ttl,self.settings.tavily_fallback_searches,
            'policy-search-v6-answer-aware-budget'], ensure_ascii=False).encode()).hexdigest()
        if self.configured and ttl and not freshness:
            cached = search_cache.get(key)
            if cached is not None:
                cached.diagnostics.cache_hit = True
                return cached
        report = self._search_with_diagnostics(query)
        self._tag_report(report,query,'requested')
        report.diagnostics.attempts=[self._attempt(query,report.diagnostics)] if self.configured else []
        if not report.sources and self.configured and report.diagnostics.stage=='complete':
            report=self._extend_report(report,query)
        if ttl and not freshness and report.sources and not report.diagnostics.rejected_counts.get('extraction_failed'):
            search_cache.put(key, report, ttl)
        return report

    def remaining_queries(self,query,diagnostic):
        used={attempt.query for attempt in diagnostic.attempts}
        return [variant for variant in fallback_queries(query)[:self.settings.tavily_fallback_searches] if variant not in used]

    def refine_with_diagnostics(self,query,sources,diagnostic):
        # Request-scoped continuation: the same three-query budget applies after generation.
        return self._extend_report(SearchReport(list(sources),diagnostic.model_copy(deep=True)),query)

    def _extend_report(self,report,query):
        seen={page.url for page in report.diagnostics.pages}|{source.url for source in report.sources}
        for variant in self.remaining_queries(query,report.diagnostics):
            try:
                extra=self._search_with_diagnostics(variant,excluded_urls=seen)
            except WebSearchError as error:
                if error.diagnostics: self._merge(report.diagnostics,error.diagnostics,variant)
                error.diagnostics=report.diagnostics
                raise
            self._tag_report(extra,variant,'city_fallback')
            self._merge(report.diagnostics,extra.diagnostics,variant)
            seen.update(page.url for page in extra.diagnostics.pages)
            if extra.sources:
                unique={source.url:source for source in [*extra.sources,*report.sources]}
                report.sources=list(unique.values())[:self.settings.tavily_max_results]
                report.diagnostics.accepted_count=len(report.sources)
                break
        return report

    @staticmethod
    def _tag_report(report,query,scope):
        report.sources=[source.model_copy(update={'search_query':query,'search_scope':scope}) for source in report.sources]
        report.diagnostics.pages=[page.model_copy(update={'search_query':query}) for page in report.diagnostics.pages]

    @staticmethod
    def _attempt(query,diagnostic):
        fields=('stage','search_count','official_count','extraction_requested','extraction_returned','body_count','accepted_count','rejected_counts')
        return WebSearchAttempt(query=query,**{field:getattr(diagnostic,field) for field in fields})

    @classmethod
    def _merge(cls,combined,extra,query):
        combined.attempts.append(cls._attempt(query,extra))
        for field in ('search_count','official_count','extraction_requested','extraction_returned','body_count'):
            setattr(combined,field,getattr(combined,field)+getattr(extra,field))
        for reason,count in extra.rejected_counts.items(): combined.rejected_counts[reason]=combined.rejected_counts.get(reason,0)+count
        combined.pages.extend(page.model_copy(update={'search_query':page.search_query or query}) for page in extra.pages)
        combined.stage=extra.stage

    def _search_with_diagnostics(self, query: str, *, excluded_urls=frozenset()) -> SearchReport:
        diagnostic = WebDiagnostics(search_query=query)
        def reject(reason):
            diagnostic.rejected_counts[reason] = diagnostic.rejected_counts.get(reason,0) + 1
        if not self.configured:
            diagnostic.stage = 'not_configured'
            return SearchReport([], diagnostic)
        if not self.settings.tavily_include_domains: raise WebSearchError('未配置联网搜索的官方站点范围。',diagnostic)
        headers = {'Authorization':'Bearer '+self.settings.tavily_api_key.get_secret_value()}
        try:
            with httpx.Client(timeout=httpx.Timeout(self.settings.tavily_timeout_seconds, connect=10), follow_redirects=False) as client:
                diagnostic.stage = 'search'
                candidate_limit = min(10, self.settings.tavily_max_results * 3)
                result = client.post('https://api.tavily.com/search', headers=headers, json={
                    'query':query[:1000], 'search_depth':'advanced', 'max_results':candidate_limit,
                    'include_domains':self.settings.tavily_include_domains, 'include_answer':False, 'include_raw_content':False})
                if result.status_code != 200: raise WebSearchError(f'联网搜索服务返回 HTTP {result.status_code}，请检查 Tavily 配置或额度。')
                candidates = {}
                results = result.json()['results']
                if not isinstance(results,list): raise ValueError('results must be a list')
                diagnostic.search_count = len(results)
                for item in results:
                    url = self.allowed_url(item.get('url'))
                    if not url: reject('url_not_allowed'); continue
                    if url in excluded_urls:
                        reject('duplicate_previous_url')
                        diagnostic.pages.append(WebPageDiagnostic(title=clean_title(str(item.get('title') or url))[:300],url=url,outcome='rejected',reason='duplicate_previous_url'))
                        continue
                    if url in candidates: reject('duplicate_search_url'); continue
                    candidates[url] = item
                    if len(candidates) >= candidate_limit: break
                diagnostic.official_count = len(candidates)
                if not candidates:
                    diagnostic.stage = 'complete'
                    return SearchReport([], diagnostic)
                candidates=dict(sorted(candidates.items(),key=lambda item:-source_priority(query,str(item[1].get('title') or ''),url=item[0])))
                diagnostic.stage = 'extract'
                diagnostic.extraction_requested = len(candidates)
                extracted = client.post('https://api.tavily.com/extract', headers=headers, json={
                    'urls':list(candidates), 'extract_depth':'advanced', 'format':'text'},
                    timeout=httpx.Timeout(self.settings.tavily_extract_timeout_seconds,connect=10))
                if extracted.status_code != 200: raise WebSearchError(f'网页正文提取返回 HTTP {extracted.status_code}，暂不能使用搜索摘要作答。')
                sources = []
                seen = set()
                results = extracted.json()['results']
                if not isinstance(results,list): raise ValueError('results must be a list')
                diagnostic.extraction_returned = len(results)
                results=sorted(results,key=lambda item:-source_priority(query,str(candidates.get(item.get('url'),{}).get('title') or ''),str(item.get('raw_content') or ''),str(item.get('url') or '')))
                diagnostic.stage = 'filter'
                for item in results:
                    url = self.allowed_url(item.get('url'))
                    # Reject redirected, unrelated or duplicated extract results.
                    if not url or url not in candidates: reject('unexpected_extract_url'); continue
                    if url in seen: reject('duplicate_extract_url'); continue
                    seen.add(url)
                    content = item.get('raw_content')
                    meta = candidates[url]
                    title = meta.get('title')
                    title = clean_title(title) if isinstance(title,str) else url
                    if not isinstance(content,str) or not content.strip():
                        reason = 'empty_body'
                    else:
                        diagnostic.body_count += 1
                        reason = relevance_reason(query,title,content,url)
                    excerpt = self.excerpt(query,content) if not reason else ''
                    if not reason:
                        reason = relevance_reason(query,title,excerpt,url)
                        if reason: reason = 'excerpt_' + reason
                    if not reason and len(sources) >= self.settings.tavily_max_results: reason = 'output_limit'
                    diagnostic.pages.append(WebPageDiagnostic(title=title[:300],url=url,outcome='rejected' if reason else 'accepted',reason=reason or 'relevant'))
                    if reason: reject(reason); continue
                    published = meta.get('published_date')
                    sources.append(WebSource(title=title[:300] if isinstance(title,str) and title else url,
                        url=url, content=excerpt, original_content_chars=len(content.strip()),
                        excerpt_start=content.strip().find(excerpt), is_truncated=excerpt!=content.strip(),
                        coverage='excerpt' if excerpt!=content.strip() else 'extracted_text',
                        published_date=published[:100] if isinstance(published,str) else None,
                        retrieved_at=datetime.now(UTC).isoformat()))
                for url, meta in candidates.items():
                    if url not in seen:
                        reject('extraction_failed')
                        diagnostic.pages.append(WebPageDiagnostic(title=clean_title(str(meta.get('title') or url))[:300],url=url,outcome='rejected',reason='extraction_failed'))
                diagnostic.accepted_count = len(sources)
                diagnostic.stage = 'complete'
                return SearchReport(sources, diagnostic)
        except WebSearchError as error:
            error.diagnostics = diagnostic
            raise
        except httpx.TimeoutException:
            raise WebSearchError('联网搜索或正文提取超时，尚未完成网络核验。',diagnostic) from None
        except httpx.HTTPError:
            raise WebSearchError('无法连接联网搜索服务，尚未完成网络核验。',diagnostic) from None
        except (ValueError, KeyError, TypeError, AttributeError):
            raise WebSearchError('联网搜索返回格式异常，尚未完成网络核验。',diagnostic) from None


def get_web_search():
    return TavilySearch(get_settings())
