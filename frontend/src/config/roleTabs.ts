export const roleTabs:Record<string,{id:string;title:string}[]>={
 admin:[{id:'dashboard',title:'运营看板'},{id:'drafts',title:'审批台'}],
 medical:[{id:'tasks',title:'用药助手'},{id:'drafts',title:'用药草稿'},{id:'profiles',title:'医护资料核实'},{id:'inbox',title:'异常待办'}],
 kitchen:[{id:'tasks',title:'菜单助手'},{id:'drafts',title:'菜单与换餐审批'},{id:'executions',title:'备餐清单'}],
 nursing:[{id:'tasks',title:'排班助手'},{id:'drafts',title:'排班草稿与照护审核'},{id:'shifts',title:'已批准排班'}],
 finance:[{id:'tasks',title:'代码核薪'},{id:'drafts',title:'核薪单与工资解释'},{id:'shifts',title:'只读工时'}],
 user:[{id:'tasks',title:'上报与换餐校验'},{id:'drafts',title:'申请记录'},{id:'executions',title:'执行清单'},{id:'shifts',title:'打卡'}],
}
