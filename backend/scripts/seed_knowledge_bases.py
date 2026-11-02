"""Create the six agent knowledge bases (idempotent).

Run after `alembic upgrade head`:
    python -m scripts.seed_knowledge_bases

The knowledge_base table has no create API yet, so this is the supported way to add
a base before uploading documents into it. Re-running only inserts missing rows.
"""
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.knowledge_base import KnowledgeBase

BASES = [
    ("policy", "政策法规库", "养老政策、补贴、长期护理保险与办理流程"),
    ("health", "健康管理库", "慢病防治、指标判读、老年健康管理与就医指引"),
    ("medication", "用药安全库", "老年人合理用药、相互作用、剂量与服药注意事项"),
    ("diet", "膳食营养库", "膳食指南、食养指南、营养风险与份量参考"),
    ("safety", "居家安全库", "跌倒预防、适老化改造、应急处置与居家风险"),
    ("mind", "心理关怀库", "情绪支持、哀伤辅导、睡眠与危机干预"),
]


def main():
    with SessionLocal() as db:
        existing = {kb.id: kb for kb in db.scalars(select(KnowledgeBase))}
        created = []
        for kb_id, name, description in BASES:
            base = existing.get(kb_id)
            if base is None:
                db.add(KnowledgeBase(id=kb_id, name=name, description=description))
                created.append(kb_id)
            elif not base.description:
                base.description = description
        db.commit()
        rows = db.scalars(select(KnowledgeBase).order_by(KnowledgeBase.id)).all()
        print("created:", created or "none")
        for row in rows:
            print(f"  {row.id:<12} {row.name}  {row.description or ''}")


if __name__ == "__main__":
    main()
