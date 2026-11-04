from app.services.menu_planning import diversity_issues


def slot(foods,meal='lunch'):
    return {'meal':meal,'options':[{'foods':foods}]}


def test_sparse_lunch_is_reported():
    assert any('至少4项' in x for x in diversity_issues([slot(['米饭','蒸蛋'])],[]))


def test_staples_can_repeat_but_dishes_are_flagged():
    previous=[slot(['米饭','番茄炒蛋','白菜','冬瓜汤'])]*2
    issues=diversity_issues([slot(['米饭','番茄炒蛋','南瓜','海带汤'])],previous)
    assert any('番茄炒蛋' in x for x in issues)
    assert not any('米饭' in x for x in issues)


def test_varied_meals_pass():
    assert not diversity_issues([slot(['小米粥','蒸蛋','红薯'],'breakfast'),slot(['米饭','清蒸鱼','炒白菜','冬瓜汤'])],[])
