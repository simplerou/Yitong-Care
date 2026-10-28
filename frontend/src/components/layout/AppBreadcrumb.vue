<script setup lang="ts">
import { useRoute } from 'vue-router'
const route = useRoute()
</script>
<template><div class="crumb" aria-label="当前位置"><RouterLink to="/home">首页</RouterLink><span class="sep">/</span><span>{{ route.meta.group }}</span><span class="sep">/</span><span>{{ route.meta.title }}</span></div></template>
