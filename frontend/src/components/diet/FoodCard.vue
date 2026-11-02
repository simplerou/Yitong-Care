<script setup lang="ts">
import type { FoodMention } from '../../api/diet'
const props = defineProps<{ foods: FoodMention[]; unknown?: string[] }>()
const flagLabels: Record<string, string> = {
  high_salt: '高盐', high_fat: '高油', high_sugar: '高糖', high_purine: '高嘌呤',
  high_potassium: '含钾较高', vitamin_k: '含维生素 K', calcium: '富含钙', protein: '蛋白质',
  vegetable: '蔬菜', fruit: '水果', staple: '主食', whole_grain: '全谷物', alcohol: '含酒精',
  caffeine: '含咖啡因', grapefruit: '西柚类', raw_risk: '生食风险', texture_hard: '质地偏硬',
  processed: '加工食品', supplement: '补充剂', plant_protein: '植物蛋白',
}
const shown = (flags: string[]) => flags.filter(flag => flag in flagLabels).slice(0, 4).map(flag => flagLabels[flag])
</script>
<template>
  <section v-if="props.foods.length || (props.unknown && props.unknown.length)" class="foods" aria-label="本次提到的食物">
    <header><b>本次提到的食物</b><span class="badge blue">{{ props.foods.length }} 种</span></header>
    <ul>
      <li v-for="food in props.foods" :key="food.canonical">
        <span class="food-name">{{ food.name }}</span>
        <span class="food-label">{{ food.label }}</span>
        <span v-for="tag in shown(food.flags)" :key="tag" class="food-tag">{{ tag }}</span>
      </li>
    </ul>
    <p v-if="props.unknown && props.unknown.length" class="food-unknown">未收录：{{ props.unknown.join('、') }}（暂无法判断成分，请核对配料表）</p>
  </section>
</template>
<style scoped>
.foods { border:1px solid var(--line); border-radius:12px; padding:10px 14px; margin:10px 0; font-size:13px; }
.foods header { display:flex; align-items:center; gap:8px; flex-wrap:wrap; }
.foods ul { list-style:none; margin:8px 0 0; padding:0; display:grid; gap:6px; }
.foods li { display:flex; align-items:baseline; gap:8px; flex-wrap:wrap; }
.food-name { font-weight:600; }
.food-label { color:var(--muted); }
.food-tag { font-size:11px; padding:1px 6px; border-radius:6px; background:var(--tint,#f2f7ff); color:var(--brand); }
.food-unknown { margin:8px 0 0; color:#94540b; }
</style>
