<script setup lang="ts">
import { computed, nextTick, reactive, ref, watch } from 'vue'
import { authApi } from '../../api/auth'
import { useRouter } from 'vue-router'
import { useRoute } from 'vue-router'
const route = useRoute(), router = useRouter(), busy = ref(false)
const registering = computed(() => route.name === 'register')
const form = reactive({ name: '', phone: '', password: '', confirm: '' })
const errors = reactive<Record<string, string>>({})
const visible = ref(false), confirmVisible = ref(false), notice = ref('')
const services = [
  { icon: 'heart', name: '健康管家', text: '关心每一次健康变化' },
  { icon: 'pill', name: '用药管家', text: '让用药多一份安心' },
  { icon: 'doc', name: '政策顾问', text: '让惠老政策更易懂' },
  { icon: 'leaf', name: '膳食营养师', text: '把营养融入每一餐' },
  { icon: 'shield', name: '安全守护', text: '关注居家的每处细节' },
  { icon: 'smile', name: '心灵陪伴', text: '让每一份心事被倾听' },
]
watch(registering, () => {
  form.password = ''; form.confirm = ''; visible.value = false; confirmVisible.value = false; notice.value = ''
  Object.keys(errors).forEach(key => delete errors[key])
})
async function submit() {
  if (busy.value) return
  Object.keys(errors).forEach(key => delete errors[key]); notice.value = ''
  if (registering.value && !form.name.trim()) errors.name = '请填写您的称呼'
  if (!/^1[3-9]\d{9}$/.test(form.phone.trim())) errors.phone = '请输入正确的 11 位手机号码'
  if (!form.password) errors.password = '请输入密码'
  else if (registering.value && (form.password.length < 8 || !/[A-Za-z]/.test(form.password) || !/\d/.test(form.password))) errors.password = '请使用至少 8 位的字母和数字组合'
  if (registering.value && form.confirm !== form.password) errors.confirm = '两次输入的密码不一致'
  if (Object.keys(errors).length) {
    await nextTick(); document.getElementById('auth-' + Object.keys(errors)[0])?.focus(); return
  }
  busy.value = true
  try {
    if (registering.value) {
      await authApi.register({ name: form.name.trim(), phone: form.phone.trim(), password: form.password })
      await router.push('/login')
      notice.value = '账号创建成功，请登录。'
    } else {
      await authApi.login(form.phone.trim(), form.password)
      form.password = ''
      window.location.hash = '/home'
      window.location.reload()
    }
  } catch (error) { notice.value = error instanceof Error ? error.message : '请求失败，请稍后重试' }
  finally { busy.value = false }

}
</script>
<template>
  <div class="auth-page">
    <header class="auth-header">
      <RouterLink to="/login" class="auth-brand" aria-label="颐养通登录"><span class="auth-logo"><AppIcon name="heart" :size="27" /></span><span><b>颐养通</b><small>YITONG CARE</small></span></RouterLink>
      <span class="auth-back">智能养老服务平台</span>
    </header>
    <main class="auth-main">
      <section class="auth-story" aria-labelledby="care-heading">
        <div class="auth-eyebrow"><span></span> 智能相伴 · 温暖每一天</div>
        <h1 id="care-heading">让关爱，更懂你。<br><span>让养老，更安心。</span></h1>
        <p class="auth-intro">从日常健康到生活陪伴，<br>颐养通与您一起，照顾生活中的点点滴滴。</p>
        <div class="auth-services"><div v-for="service in services" :key="service.name" class="auth-service"><span><AppIcon :name="service.icon" :size="22" /></span><div><b>{{ service.name }}</b><p>{{ service.text }}</p></div></div></div>
        <div class="auth-story-note"><AppIcon name="heart" :size="18" /> 科技有温度，关爱在身边。</div>
      </section>
      <section class="auth-form-card" :aria-labelledby="registering ? 'register-heading' : 'login-heading'">
        <div class="auth-card-top"><span class="auth-card-symbol"><AppIcon :name="registering ? 'smile' : 'home'" :size="25" /></span><span>您的智慧养老生活，从这里开始</span></div>
        <h2 :id="registering ? 'register-heading' : 'login-heading'">{{ registering ? '很高兴认识您' : '欢迎回来' }}</h2>
        <p class="auth-subtitle">{{ registering ? '创建颐养通账号，开启温暖的陪伴。' : '登录颐养通，让关爱与您常伴。' }}</p>
        <div class="auth-tabs" role="group" aria-label="当前账号页面"><span :aria-current="!registering ? 'page' : undefined">账号登录</span><span :aria-current="registering ? 'page' : undefined">注册账号</span></div>
        <form novalidate :aria-busy="busy" @submit.prevent="submit"><fieldset :disabled="busy" class="auth-fieldset">
          <div v-if="registering" class="auth-field"><label for="auth-name">您的称呼</label><input id="auth-name" v-model="form.name" autocomplete="nickname" maxlength="30" placeholder="请输入您的称呼" :aria-invalid="!!errors.name" :aria-describedby="errors.name ? 'error-name' : undefined"><p v-if="errors.name" id="error-name" class="auth-error">{{ errors.name }}</p></div>
          <div class="auth-field"><label for="auth-phone">手机号码</label><input id="auth-phone" v-model="form.phone" type="tel" inputmode="tel" autocomplete="username" maxlength="11" placeholder="请输入手机号码" :aria-invalid="!!errors.phone" :aria-describedby="errors.phone ? 'error-phone' : undefined"><p v-if="errors.phone" id="error-phone" class="auth-error">{{ errors.phone }}</p></div>
          <div class="auth-field"><label for="auth-password">{{ registering ? '设置密码' : '登录密码' }}</label><div class="auth-password"><input id="auth-password" v-model="form.password" :type="visible ? 'text' : 'password'" :autocomplete="registering ? 'new-password' : 'current-password'" :placeholder="registering ? '至少 8 位，包含字母和数字' : '请输入密码'" :aria-invalid="!!errors.password" :aria-describedby="errors.password ? 'error-password' : undefined"><button type="button" :aria-pressed="visible" aria-controls="auth-password" :aria-label="visible ? '隐藏密码' : '显示密码'" :title="visible ? '隐藏密码' : '显示密码'" @click="visible = !visible"><AppIcon :name="visible ? 'eye-off' : 'eye'" :size="20" /></button></div><p v-if="errors.password" id="error-password" class="auth-error">{{ errors.password }}</p></div>
          <div v-if="registering" class="auth-field"><label for="auth-confirm">确认密码</label><div class="auth-password"><input id="auth-confirm" v-model="form.confirm" :type="confirmVisible ? 'text' : 'password'" autocomplete="new-password" placeholder="请再次输入密码" :aria-invalid="!!errors.confirm" :aria-describedby="errors.confirm ? 'error-confirm' : undefined"><button type="button" :aria-pressed="confirmVisible" aria-controls="auth-confirm" :aria-label="confirmVisible ? '隐藏确认密码' : '显示确认密码'" :title="confirmVisible ? '隐藏确认密码' : '显示确认密码'" @click="confirmVisible = !confirmVisible"><AppIcon :name="confirmVisible ? 'eye-off' : 'eye'" :size="20" /></button></div><p v-if="errors.confirm" id="error-confirm" class="auth-error">{{ errors.confirm }}</p></div>
          <button class="auth-submit" type="submit">{{ busy ? '正在提交…' : registering ? '创建账号' : '登录' }}<AppIcon name="arrow" :size="19" /></button>
          <p v-if="notice" class="auth-notice" role="status">{{ notice }}</p>
        </fieldset></form>
        <p class="auth-switch">{{ registering ? '已经有账号？' : '还没有账号？' }}<RouterLink :to="registering ? '/login' : '/register'">{{ registering ? '立即登录' : '立即注册' }}</RouterLink></p>
        <div class="auth-preview"><AppIcon name="info" :size="16" /><span>请妥善保管账号，切勿向他人透露密码。</span></div>
      </section>
    </main>
    <footer class="auth-footer"><span>颐养通 · 智能养老服务平台</span><span>用心守护，让每一天都安心</span></footer>
  </div>
</template>
<style scoped>
.auth-page { --auth-muted: #53647e; --auth-error: #b4232b; min-height: 100dvh; background: radial-gradient(ellipse at 8% 46%, var(--brand-100) 0, transparent 53%), var(--bg); font-size: 16px; }
.auth-header { max-width: 1320px; margin: auto; padding: 28px 48px; display: flex; align-items: center; justify-content: space-between; gap: 20px; }
.auth-brand { display: flex; align-items: center; gap: 12px; }.auth-logo { display: grid; place-items: center; width: 48px; height: 48px; background: var(--brand); color: var(--card); border-radius: 15px; box-shadow: var(--shadow-sm); }
.auth-brand b { display: block; font-size: 24px; letter-spacing: 3px; line-height: 1.2; }.auth-brand small { font-size: 10px; letter-spacing: 2px; color: var(--auth-muted); }.auth-back { display: flex; align-items: center; gap: 10px; min-height: 44px; color: var(--auth-muted); font-size: 14px; }
.auth-main { max-width: 1180px; margin: 28px auto 48px; padding: 0 32px; display: grid; grid-template-columns: 1fr 460px; gap: 80px; align-items: center; }
.auth-story { padding: 20px 0; }.auth-eyebrow { display: flex; align-items: center; gap: 10px; color: var(--brand-ink); font-size: 14px; font-weight: 600; letter-spacing: 2px; }.auth-eyebrow span { width: 7px; height: 7px; border-radius: 50%; background: var(--brand); }
.auth-story h1 { font-size: clamp(32px, 3.5vw, 46px); line-height: 1.45; letter-spacing: -1px; margin: 22px 0; }.auth-story h1 span { color: var(--brand); }.auth-intro { color: var(--auth-muted); line-height: 1.9; margin-bottom: 32px; }
.auth-services { display: grid; grid-template-columns: repeat(2, 1fr); gap: 25px 18px; }.auth-service { display: flex; align-items: center; gap: 12px; }.auth-service > span { width: 44px; height: 44px; display: grid; place-items: center; background: var(--card); color: var(--brand-deep); border-radius: 12px; border: 1px solid var(--line); }.auth-service b { font-size: 15px; }.auth-service p { font-size: 12px; color: var(--auth-muted); margin: 3px 0 0; }.auth-story-note { margin-top: 40px; border-top: 1px solid var(--line-2); padding-top: 23px; display: flex; gap: 10px; align-items: center; font-size: 14px; color: var(--auth-muted); }
.auth-form-card { padding: 32px 36px 24px; background: var(--card); border: 1px solid var(--line); border-radius: 24px; box-shadow: var(--shadow); }.auth-card-top { display: flex; align-items: center; gap: 12px; color: var(--auth-muted); font-size: 12px; }.auth-card-symbol { display: grid; place-items: center; width: 46px; height: 46px; background: var(--brand-50); color: var(--brand); border-radius: 14px; }.auth-form-card h2 { margin: 22px 0 6px; font-size: 29px; }.auth-subtitle { color: var(--auth-muted); font-size: 14px; margin: 0 0 24px; }.auth-tabs { display: grid; grid-template-columns: 1fr 1fr; background: var(--bg); border-radius: 10px; padding: 4px; margin-bottom: 24px; }.auth-tabs span { display: grid; place-items: center; min-height: 44px; border-radius: 8px; font-size: 15px; color: var(--auth-muted); }.auth-tabs span[aria-current] { color: var(--brand-deep); background: var(--card); box-shadow: var(--shadow-xs); font-weight: 600; }
.auth-fieldset { border: 0; padding: 0; margin: 0; min-width: 0; }.auth-fieldset:disabled { opacity: .7; }
.auth-field { margin-bottom: 17px; }.auth-field label { display: block; font-size: 14px; font-weight: 600; margin-bottom: 7px; }.auth-field input { width: 100%; min-width: 0; height: 49px; padding: 0 14px; border: 1px solid var(--line-2); border-radius: 9px; background: var(--card); font-size: 16px; }.auth-field input::placeholder { color: var(--auth-muted); font-size: 14px; }.auth-password { position: relative; }.auth-password input { padding-right: 54px; }.auth-password button { position: absolute; right: 4px; top: 2px; min-height: 44px; min-width: 44px; display: grid; place-items: center; border: none; background: transparent; color: var(--brand-deep); font-size: 13px; }.auth-field input[aria-invalid=true] { border-color: var(--auth-error); }.auth-error { margin: 5px 0 0; font-size: 13px; color: var(--auth-error); }
.auth-submit { width: 100%; min-height: 50px; border: none; border-radius: 10px; color: var(--card); background: var(--brand); display: flex; justify-content: center; align-items: center; gap: 12px; font-size: 16px; font-weight: 600; margin-top: 24px; transition: background 180ms; }.auth-submit:hover { background: var(--brand-deep); }.auth-switch { text-align: center; font-size: 14px; color: var(--auth-muted); margin: 22px 0; }.auth-switch a { display: inline-flex; align-items: center; min-height: 44px; color: var(--brand-deep); font-weight: 600; margin-left: 8px; }.auth-preview { border-top: 1px solid var(--line); padding-top: 16px; display: flex; gap: 8px; align-items: center; color: var(--auth-muted); font-size: 12px; }.auth-notice { background: var(--brand-50); color: var(--brand-ink); padding: 12px; border-radius: 8px; font-size: 14px; }.auth-footer { max-width: 1220px; padding: 0 24px 24px; margin: auto; display: flex; justify-content: space-between; gap: 12px; color: var(--auth-muted); font-size: 12px; }
.auth-page :is(a, button, input):focus-visible { outline: 3px solid var(--brand); outline-offset: 3px; }
@media (max-width: 1024px) { .auth-main { gap: 36px; grid-template-columns: 1fr 420px; }.auth-services { grid-template-columns: 1fr; gap: 16px; }.auth-service p { display: none; } }
@media (max-width: 760px) { .auth-header { padding: 20px; }.auth-main { display: block; padding: 0 20px; margin: 8px auto 32px; max-width: 500px; }.auth-story { padding: 8px 4px 24px; }.auth-story h1 { font-size: 30px; margin: 12px 0; }.auth-intro, .auth-services, .auth-story-note { display: none; }.auth-form-card { padding: 26px 24px 22px; border-radius: 20px; }.auth-footer { flex-direction: column; align-items: center; gap: 4px; }.auth-card-top { font-size: 12px; } }
@media (prefers-reduced-motion: reduce) { .auth-submit { transition: none; } }
</style>
