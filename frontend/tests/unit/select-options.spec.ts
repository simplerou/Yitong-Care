import { expect,it } from 'vitest'
import { Fragment,h,createCommentVNode,createTextVNode } from 'vue'
import { selectOptions } from '../../src/components/common/selectOptions'
it('保留动态选项的数字值和禁用占位项，忽略未渲染分支',()=>{
 const nodes=[h('option',{value:'',disabled:''},'请选择'),createCommentVNode('v-if'),h(Fragment,null,[3,5,10].map(n=>h('option',{value:n},String(n))))]
 const result=selectOptions(nodes)
 expect(result).toEqual([{value:'',label:'请选择',disabled:true},...[3,5,10].map(n=>({value:n,label:String(n),disabled:false}))])
})
it('组合插值文本，支持未显式填写value的只读模型选项',()=>{
 expect(selectOptions([h('option',null,[createTextVNode('模型名称'),createTextVNode(' · 1024 维')])])).toEqual([{value:'模型名称 · 1024 维',label:'模型名称 · 1024 维',disabled:false}])
})
it('重新读取异步选项时不保留上一份选项',()=>{
 expect(selectOptions([])).toEqual([])
 expect(selectOptions([h('option',{value:'new'},'新会话')])).toEqual([{value:'new',label:'新会话',disabled:false}])
})
