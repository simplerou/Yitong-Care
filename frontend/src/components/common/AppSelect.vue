<script setup lang="ts">
import { computed,ref,useAttrs,useSlots } from 'vue'
import { ElSelect,ElOption } from 'element-plus'
import 'element-plus/es/components/select/style/css'
import 'element-plus/es/components/option/style/css'
import { selectOptions } from './selectOptions'
defineOptions({inheritAttrs:false})
const props=defineProps<{modelValue?:string|number;value?:string|number;modelModifiers?:{number?:boolean}}>()
const emit=defineEmits<{'update:modelValue':[value:string|number];change:[value:string|number]}>()
const attrs=useAttrs(),slots=useSlots()
// Read the slot on each render: v-for and v-if options can change after an API request.
function options(){return selectOptions(slots.default?.()||[])}
const expanded=ref(false)
const selected=computed(()=>props.modelValue??props.value)
function update(value:string|number){emit('update:modelValue',props.modelModifiers?.number?Number(value):value)}
</script>
<template><ElSelect v-bind="attrs" class="app-select" :class="{'is-open':expanded}" :placeholder="options().find(option=>option.value==='')?.label||'请选择'" placement="bottom-start" :fallback-placements="['bottom-start','top-start']" :offset="6" @visible-change="expanded=$event" :model-value="selected??options()[0]?.value" :automatic-dropdown="false" :teleported="true" popper-class="app-select-options" :show-arrow="false" @update:model-value="update" @change="emit('change',$event)"><ElOption v-for="(option,index) in options()" :key="`${typeof option.value}:${option.value}:${index}`" :value="option.value" :label="option.label" :disabled="option.disabled"/></ElSelect></template>
