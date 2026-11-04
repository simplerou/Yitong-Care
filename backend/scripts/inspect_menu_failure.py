"""Read the latest local menu failure without calling MySQL, Qwen or Tavily."""
import argparse
import json
from pathlib import Path
from app.services.menu_diagnostics import get_menu_diagnostic_dir

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('path',nargs='?',help='不传时读取最新菜单诊断')
    parser.add_argument('--candidate',action='store_true',help='同时打印失败当天的原始候选，仅用于本机排查')
    args=parser.parse_args()
    files=sorted(get_menu_diagnostic_dir().glob('menu-*.json'))
    path=Path(args.path) if args.path else files[-1] if files else None
    if not path:print('没有菜单失败诊断；旧版失败未留存输出，无法追溯其具体原因。');return 1
    data=json.loads(path.read_text(encoding='utf-8'))
    print('诊断文件：'+str(path))
    print('失败日期序号：第'+str(data['day'])+'天')
    print('具体检查：'+json.dumps(data.get('issues',[]),ensure_ascii=False))
    print('生成设置：'+json.dumps(data.get('request',{}),ensure_ascii=False))
    print('已完成天数：'+str(data.get('accepted_days',0)))
    if args.candidate:print('失败候选：'+json.dumps(data.get('attempts',[]),ensure_ascii=False,indent=2))
    print('只读取本地诊断，没有重新生成、访问数据库或修改菜单。')
    return 0
if __name__=='__main__':raise SystemExit(main())
