import pytest
from sqlalchemy import event, select, func
from app.models.resident import Resident, ResidentChange, ResidentAssignment
from scripts.seed_residents import read_dataset, generate, import_dataset


def test_100_sample_import_is_audited_and_idempotent(client):
    _,_,factory=client
    rows=read_dataset()
    assert len(rows)==100
    assert len({row[1].name for row in rows})==100
    assert sum(data.status=='in_care' for _,data in rows)==90
    assert len({data.location for _,data in rows if data.status=='in_care'})==90
    assert not any('测试' in data.name for _,data in rows)
    assert {data.location.split('楼')[0] for _,data in rows if data.location}==set('ABCD')
    assert all(not data.contact_phone for _,data in rows)
    assert generate()['residents'][0]['data']['name']==rows[0][1].name
    with factory() as db:
        assert import_dataset(db,rows)=={'created':100,'skipped':0,'updated':0,'batch_total':100}
        assert db.scalar(select(func.count()).select_from(ResidentChange))==100
        assert db.scalar(select(func.count()).select_from(ResidentAssignment))==0
        first=db.scalar(select(Resident).where(Resident.record_no=='DEMO202611-001'))
        first.care_notes='管理员人工调整';db.commit()
        assert import_dataset(db,rows)=={'created':0,'skipped':100,'updated':0,'batch_total':100}
        db.refresh(first)
        assert first.care_notes=='管理员人工调整'
        assert db.scalar(select(func.count()).select_from(Resident))==100
        assert db.scalar(select(func.count()).select_from(ResidentChange))==100


def test_failure_rolls_back_whole_batch(client):
    _,_,factory=client
    with factory() as db:
        def fail_partway(session, *_):
            if any(isinstance(row,Resident) and row.record_no=='DEMO202611-025' for row in session.new):
                raise RuntimeError('模拟导入失败')
        event.listen(db,'before_flush',fail_partway)
        try:
            with pytest.raises(RuntimeError):import_dataset(db,read_dataset())
        finally:event.remove(db,'before_flush',fail_partway)
        assert db.scalar(select(func.count()).select_from(Resident))==0
        assert db.scalar(select(func.count()).select_from(ResidentChange))==0


def test_refresh_old_labels_preserves_manual_details_and_is_idempotent(client):
    _,_,factory=client
    rows=read_dataset()
    with factory() as db:
        import_dataset(db,rows)
        one=db.scalar(select(Resident).where(Resident.record_no=='DEMO202611-001'))
        one.name='测试·赵建国';one.location='演示楼 / 1层 / 101室 / 01床';one.care_notes='人工照护备注'
        two=db.scalar(select(Resident).where(Resident.record_no=='DEMO202611-002'))
        two.name='人工更正姓名';two.location='管理员调整的位置'
        db.commit()
        result=import_dataset(db,rows,refresh_labels=True)
        assert result['updated']==1 and result['created']==0
        db.refresh(one);db.refresh(two)
        assert one.name=='赵建国' and one.location.startswith('A楼')
        assert one.care_notes=='人工照护备注' and one.version==2
        assert two.name=='人工更正姓名' and two.location=='管理员调整的位置'
        assert db.scalar(select(func.count()).select_from(ResidentChange))==101
        assert import_dataset(db,rows,refresh_labels=True)['updated']==0
