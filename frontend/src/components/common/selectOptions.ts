import { isVNode,type VNode } from 'vue'
interface SelectOption {value:string|number;label:string;disabled:boolean}
function text(value:unknown):string {
 if(Array.isArray(value))return value.map(text).join('')
 if(isVNode(value))return text(value.children)
 return typeof value==='string'||typeof value==='number'?String(value):''
}
export function selectOptions(nodes:VNode[]):SelectOption[]{
 const result:SelectOption[]=[]
 function visit(node:unknown){
  if(Array.isArray(node)){node.forEach(visit);return}
  if(!isVNode(node))return
  if(node.type==='option'){
   const label=text(node.children),value=node.props?.value??label
   result.push({label,value,disabled:node.props?.disabled===''||node.props?.disabled===true})
  }else if(Array.isArray(node.children))node.children.forEach(visit)
 }
 nodes.forEach(visit)
 return result
}
