<script setup lang="ts">defineProps<{ index: number }>()</script>
<template><button class="cite" :aria-label="`查看引用 ${index} 原文`">{{ index }}</button></template>
