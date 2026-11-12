export interface RoleLink {label:string;path:string;icon:string;tab?:string;task?:string}
export const roleNames:Record<string,string>={admin:'院长',medical:'医务室',kitchen:'食堂',nursing:'护理部',finance:'财务部',user:'护工'}
export const roleNavigation:Record<string,RoleLink[]>={
 admin:[{label:'院长 Agent · 运营看板',path:'/operations',icon:'home',tab:'dashboard'},{label:'审批台',path:'/operations',icon:'shield',tab:'drafts'},{label:'注册审核',path:'/account-reviews',icon:'doc'}],
 medical:[{label:'医务室 Agent',path:'/operations',icon:'pill',tab:'tasks'},{label:'用药草稿',path:'/operations',icon:'doc',tab:'drafts'},{label:'医护资料核实',path:'/operations',icon:'heart',tab:'profiles'},{label:'异常待办',path:'/operations',icon:'shield',tab:'inbox'}],
 kitchen:[{label:'食堂 Agent',path:'/operations',icon:'leaf',tab:'tasks'},{label:'菜单与换餐草稿',path:'/operations',icon:'doc',tab:'drafts'},{label:'备餐清单',path:'/operations',icon:'clipboard',tab:'executions'}],
 nursing:[{label:'护理部 Agent',path:'/operations',icon:'shield',tab:'tasks'},{label:'护工账号与分配',path:'/caregivers',icon:'smile'},{label:'老人档案',path:'/residents',icon:'heart'},{label:'排班查看',path:'/operations',icon:'history',tab:'shifts'},{label:'排班草稿与照护审核',path:'/operations',icon:'doc',tab:'drafts'}],
 finance:[{label:'财务部 Agent',path:'/operations',icon:'doc',tab:'tasks'},{label:'工时核对',path:'/operations',icon:'history',tab:'shifts'},{label:'核薪与工资解释',path:'/operations',icon:'clipboard',tab:'drafts'}],
 user:[{label:'护工 Agent · 异常上报',path:'/operations',icon:'shield',tab:'tasks',task:'incident'},{label:'打卡',path:'/operations',icon:'history',tab:'shifts'},{label:'执行清单',path:'/operations',icon:'clipboard',tab:'executions'},{label:'换餐校验',path:'/operations',icon:'leaf',tab:'tasks',task:'meal_swap'},{label:'负责老人',path:'/residents',icon:'heart'}],
}
