import test from 'node:test'
import assert from 'node:assert/strict'
import { chunkText, embed, cosine, highlight } from '../../src/demo/rag.js'

test('空文档不产生切块，长句分割后正文不丢失', () => {
  assert.deepEqual(chunkText('',220,30),[])
  const text = '长期护理保险申请材料'.repeat(60)
  const chunks=chunkText(text,100,0)
  assert.equal(chunks.join(''),text)
  assert.ok(chunks.every(c=>c.length<=100))
})
test('相邻片段按完整句子保留重叠', () => {
  const sentences=['测量血压后记录数值。','平时保持均衡的饮食。','运动应根据身体情况。']
  const chunks=chunkText(sentences.join(''),22,11)
  assert.equal(chunks[1],sentences[1]+sentences[2])
})
test('演示向量归一化且同文档余弦接近一', () => {
  const v=embed('老年人跌倒后应该怎么处理')
  assert.equal(v.length,384)
  assert.ok(Math.abs(cosine(v,v)-1)<1e-6)
  assert.ok(embed('').every(n=>n===0))
})
test('高亮保留关键词并转义用户或文档中的 HTML', () => {
  const output=highlight('<img src=x onerror=alert(1)>跌倒预防','跌倒')
  assert.ok(output.includes('<mark>跌倒</mark>'))
  assert.ok(!output.includes('<img'))
  assert.ok(output.includes('&lt;img'))
})
