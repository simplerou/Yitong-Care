"""Read-only MCP connection check. Never print remote credentials or resident data."""
import sys
from app.services.howtocook import candidates
from app.core.exceptions import BusinessError

def main():
    try:result=candidates()
    except BusinessError as error:
        print(error.message);return 1
    if result['status']!='success':
        print('HowToCook 未启用；请填写 HOWTOCOOK_MCP_URL 并设置 HOWTOCOOK_ENABLED=true。');return 1
    print(f"HowToCook MCP 连接成功，读取 {result['count']} 份候选菜谱。")
    for recipe in result['recipes'][:5]:print(f"- {recipe['name']}（{len(recipe['ingredients'])} 项食材）")
    print('只查询外部食谱，没有读取老人档案、调用大模型或保存菜单。')
    return 0

if __name__=='__main__':sys.exit(main())
