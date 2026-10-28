const base = (import.meta.env.VITE_API_BASE || '/api').replace(/\/$/, '')

export class ApiError extends Error {
  constructor(message: string, public status: number) { super(message) }
}

export async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const controller = new AbortController()
  const abort = () => controller.abort()
  options.signal?.addEventListener('abort', abort, { once: true })
  if (options.signal?.aborted) controller.abort()
  const timer = setTimeout(abort, 60_000)
  const headers = new Headers(options.headers)
  if (options.body && !(options.body instanceof FormData)) headers.set('Content-Type', 'application/json')
  try {
    const response = await fetch(`${base}${path}`, { ...options, headers, signal: controller.signal })
    if (!response.ok) {
      let message = `请求失败（${response.status}）`
      try {
        const data = await response.json()
        if (typeof data.detail === 'string') message = data.detail
        else if (Array.isArray(data.detail)) message = data.detail[0]?.msg || message
      } catch { /* 代理或服务异常可能返回非 JSON */ }
      throw new ApiError(message, response.status)
    }
    if (response.status === 204) return undefined as T
    return await response.json() as T
  } catch (error) {
    if (error instanceof ApiError) throw error
    if (controller.signal.aborted) throw new ApiError('请求已取消或超时，请重试。', 0)
    throw new ApiError('无法连接后端，请确认后端服务已启动。', 0)
  } finally {
    clearTimeout(timer)
    options.signal?.removeEventListener('abort', abort)
  }
}
