"""Batch import local guideline files into their knowledge bases.

Runs the full pipeline against a live backend:
    1. upload (POST /documents)
    2. wait for parsing
    3. save chunks (POST /documents/{id}/chunks)
    4. embed + index (POST /documents/{id}/embeddings)
    5. wait for the embedding task

Idempotent: a document with the same name in the same knowledge base is not uploaded
twice, and an already vectorized document is skipped. Re-run to resume failures.

    python -m scripts.import_documents --dry-run
    python -m scripts.import_documents --only safety
    python -m scripts.import_documents --chunk-size 500 --overlap 50
"""
import argparse
import os
import json
import time
from pathlib import Path

import httpx
from pypdf import PdfReader

DATA = Path('/Users/laiguanrui/杭电高端就业培训/项目/颐养通-智能养老服务平台/项目文档/data')
PREFIX = {'政策': 'policy', '健康': 'health', '用药': 'medication',
          '膳食': 'diet', '安全': 'safety', '心灵': 'mind'}
MIME = {'.pdf': 'application/pdf', '.txt': 'text/plain', '.md': 'text/markdown',
        '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'}


def kb_for(path: Path) -> str:
    for prefix, kb in PREFIX.items():
        if path.name.startswith(prefix):
            return kb
    return 'policy'


def existing_docs(client: httpx.Client) -> dict[tuple[str, str], dict]:
    found: dict[tuple[str, str], dict] = {}
    page = 1
    while True:
        response = client.get('/documents', params={'page': page, 'page_size': 100})
        response.raise_for_status()
        body = response.json()
        for item in body['items']:
            found[(item['kb_id'], item['name'])] = item
        if page * body['page_size'] >= body['total']:
            return found
        page += 1


def wait_document(client: httpx.Client, doc_id: str, timeout: float = 300) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        doc = client.get(f'/documents/{doc_id}').json()
        if doc['status'] in {'parsed', 'chunked', 'vectorized', 'failed'}:
            return doc
        time.sleep(2)
    raise TimeoutError(f'解析超时：{doc_id}')


def save_chunks(client: httpx.Client, doc_id: str, size: int, overlap: int) -> dict:
    response = client.post(f'/documents/{doc_id}/chunks', json={'size': size, 'overlap': overlap})
    response.raise_for_status()
    return response.json()


def embed(client: httpx.Client, doc_id: str, batch_size: int, timeout: float = 1800) -> dict:
    response = client.post(f'/documents/{doc_id}/embeddings', json={'batch_size': batch_size})
    response.raise_for_status()
    task = response.json()
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        task = client.get(f"/embeddings/tasks/{task['id']}").json()
        if task['status'] in {'succeeded', 'failed'}:
            return task
        progress = (task['status'], task['phase'], task['progress'])
        if progress != last:
            print(f"      向量化 {task['status']}/{task['phase']} {task['progress']}%", flush=True)
            last = progress
        time.sleep(3)
    raise TimeoutError(f'向量化超时：{doc_id}')


def encrypted_pdf(path: Path) -> bool:
    if path.suffix.lower() != '.pdf':
        return False
    try:
        return PdfReader(str(path)).is_encrypted
    except Exception:
        return False


def import_file(client: httpx.Client, path: Path, kb: str, seen: dict, args) -> dict:
    record = {'name': path.name, 'kb': kb, 'status': 'pending', 'seconds': 0}
    if encrypted_pdf(path):
        record.update(status='skipped_encrypted', note='PDF 带加密标记，未导入；请用对应 TXT 版本')
        return record
    started = time.time()
    key = (kb, path.name)
    doc = seen.get(key)

    if doc and doc['status'] == 'vectorized' and doc['vector_count'] and not args.force:
        record.update(status='skipped', doc_id=doc['id'], chunks=doc['chunk_count'],
                      vectors=doc['vector_count'], note='已入库')
        record['seconds'] = round(time.time() - started, 1)
        return record

    if doc is None:
        with path.open('rb') as handle:
            response = client.post('/documents',
                                   files={'file': (path.name, handle, MIME.get(path.suffix.lower(), 'application/octet-stream'))},
                                   data={'kb_id': kb, 'source': '公开资料导入'})
        response.raise_for_status()
        doc = response.json()
        record['doc_id'] = doc['id']
        print(f"      上传 {doc['id'][:8]} 解析中…", flush=True)
    else:
        record['doc_id'] = doc['id']
        record['note'] = '复用已有文档'

    doc = wait_document(client, doc['id'])
    if doc['status'] == 'failed':
        record.update(status='failed', error=doc.get('error_message') or '解析失败')
        record['seconds'] = round(time.time() - started, 1)
        return record

    if not doc.get('chunk_count') or doc['status'] == 'parsed':
        result = save_chunks(client, doc['id'], args.chunk_size, args.overlap)
        record['chunks'] = result['count']
        print(f"      切块 {result['count']} 段", flush=True)
    else:
        record['chunks'] = doc['chunk_count']

    if args.skip_vectors:
        record.update(status='chunked')
        record['seconds'] = round(time.time() - started, 1)
        return record

    task = embed(client, doc['id'], args.batch_size)
    if task['status'] != 'succeeded':
        record.update(status='failed', error=task.get('error_message') or '向量化失败')
        record['seconds'] = round(time.time() - started, 1)
        return record
    final = client.get(f"/documents/{doc['id']}").json()
    record.update(status='done', chunks=final['chunk_count'], vectors=final['vector_count'])
    record['seconds'] = round(time.time() - started, 1)
    return record


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--base', default='http://127.0.0.1:8000/api')
    parser.add_argument('--data', default=str(DATA))
    parser.add_argument('--only', default='', help='只导入某个知识库：policy/health/medication/diet/safety/mind')
    parser.add_argument('--chunk-size', type=int, default=500)
    parser.add_argument('--overlap', type=int, default=50)
    parser.add_argument('--batch-size', type=int, default=16, choices=[8, 16, 32])
    parser.add_argument('--skip-vectors', action='store_true')
    parser.add_argument('--force', action='store_true', help='已入库文档也重新上传（会产生重复文档）')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    data = Path(args.data)
    files = sorted(path for path in data.iterdir()
                   if path.suffix.lower() in MIME and not path.name.startswith('_'))
    if args.only:
        files = [path for path in files if kb_for(path) == args.only]
    if not files:
        print('没有找到可导入的文件')
        return

    with httpx.Client(base_url=args.base, timeout=httpx.Timeout(120, connect=10)) as client:
        token = os.environ.get('YITONG_AUTH_TOKEN', '').strip()
        if not token:
            raise SystemExit('请先登录，并通过 YITONG_AUTH_TOKEN 环境变量提供登录凭证。')
        client.headers['Authorization'] = 'Bearer ' + token
        seen = existing_docs(client)
        print(f'待处理 {len(files)} 份，知识库已有 {len(seen)} 份文档')
        if args.dry_run:
            for path in files:
                doc = seen.get((kb_for(path), path.name))
                print(f'  {kb_for(path):<11} {path.name}  ->  {doc["status"] if doc else "新增"}')
            return

        records = []
        for index, path in enumerate(files, 1):
            kb = kb_for(path)
            print(f'[{index}/{len(files)}] {kb:<11} {path.name}', flush=True)
            try:
                record = import_file(client, path, kb, seen, args)
            except Exception as error:  # noqa: BLE001 - keep going, report per file
                record = {'name': path.name, 'kb': kb, 'status': 'error',
                          'error': f'{type(error).__name__}: {str(error)[:200]}', 'seconds': 0}
            records.append(record)
            print(f"      -> {record['status']}  {record.get('chunks', '-')} 段  "
                  f"{record.get('vectors', '-')} 向量  {record.get('seconds', '-')}s"
                  + (f"  错误：{record['error']}" if record.get('error') else ''), flush=True)

    report = {'base': args.base, 'chunk_size': args.chunk_size, 'overlap': args.overlap,
              'records': records}
    target = Path(__file__).resolve().parents[1] / 'var' / 'import-report.json'
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')

    counts: dict[str, int] = {}
    for record in records:
        counts[record['status']] = counts.get(record['status'], 0) + 1
    print('\n完成：' + '，'.join(f'{key} {value}' for key, value in sorted(counts.items())))
    print('报告：' + str(target))


if __name__ == '__main__':
    main()
