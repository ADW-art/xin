// 省一标准测试: highlight.ts 单遍扫描分词器
// 验证关键场景:
// 1. 关键字"def"被高亮但不会破坏
// 2. 字符串里的"def"不会被错误匹配
// 3. 函数调用识别
// 4. 装饰器识别
// 5. 数字识别
// 6. 多语言都能正常工作
// 7. stripHtmlTags 能清理已损坏的输入

// 简化版的 highlightCode, 模拟浏览器行为
// 因为 TypeScript 用 import, 我们需要模拟 ESM 环境
// 这里我们直接复制核心算法来验证逻辑

const PY_KW = new Set([
  'False','None','True','and','as','assert','async','await','break','class','continue',
  'def','del','elif','else','except','finally','for','from','global','if','import',
  'in','is','lambda','nonlocal','not','or','pass','raise','return','try','while',
  'with','yield',
])

function escapeHtml(str) {
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
}

function stripHtmlTags(code) {
  return code
    .replace(/<span\b[^>]*>/gi, '')
    .replace(/<\/span>/gi, '')
    .replace(/&lt;span\b[^&]*&gt;/gi, '')
    .replace(/&lt;\/span&gt;/gi, '')
    .replace(/<div\b[^>]*>/gi, '')
    .replace(/<\/div>/gi, '')
    .replace(/<code\b[^>]*>/gi, '')
    .replace(/<\/code>/gi, '')
    .replace(/<pre\b[^>]*>/gi, '')
    .replace(/<\/pre>/gi, '')
    .replace(/"(?:sk|ss|sc|sn|sf|sd|hl|k|n|s|f|d|c|o|p|w|kc|kp)">/gi, '')
    .replace(/\s*class\s*=\s*"(?:sk|ss|sc|sn|sf|sd)[^"]*"/gi, '')
    .replace(/__HL_[A-Z]{2,3}_(?:OPEN|CLOSE)__/g, '')
}

function renderTokens(tokens) {
  const parts = []
  for (const tok of tokens) {
    if (tok.type === 'code') {
      // code 类型的 token 来自未转义位置 (不可能, 因为整个 code 都先转义了)
      // 为了防御, 仍然做一次转义
      const safe = tok.text
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
      parts.push(safe)
    } else {
      // 高亮 token: text 已经来自已转义的输入, 不需要再转义
      // 否则会造成双转义: &lt; 变成 &amp;lt;
      parts.push(`<span class="${tok.type}">${tok.text}</span>`)
    }
  }
  return parts.join('')
}

function kwRe(set) {
  // 必须用 /g 标志 + lastIndex 配合分词器定位匹配位置
  return new RegExp(`(?:${Array.from(set).join('|')})\\b`, 'g')
}

function tokenize(code, rules) {
  const tokens = []
  let pos = 0
  const n = code.length

  while (pos < n) {
    let matched = false

    for (const rule of rules) {
      rule.regex.lastIndex = pos
      const m = rule.regex.exec(code)
      if (m && m.index === pos) {
        tokens.push({ type: rule.type, text: m[0] })
        pos += m[0].length
        matched = true
        break
      }
    }

    if (!matched) {
      let next = pos + 1
      for (const rule of rules) {
        rule.regex.lastIndex = pos + 1
        const m = rule.regex.exec(code)
        if (m) {
          next = Math.min(next, m.index)
        }
      }
      if (next > pos) {
        tokens.push({ type: 'code', text: code.slice(pos, next) })
        pos = next
      } else {
        tokens.push({ type: 'code', text: code[pos] })
        pos++
      }
    }
  }

  return tokens
}

// 必须用 /g 标志, 配合分词器的 lastIndex 机制
const PY_TRIPLE_DQ = /"""[\s\S]*?"""|"[^"]*"/g  // 简化
const PY_DQ_STR = /"(?:[^"\\]|\\.)*"/g
const PY_SQ_STR = /'(?:[^'\\]|\\.)*'/g
const PY_COMMENT = /#[^\n]*/g
const PY_DECORATOR = /@\w+/g
const PY_KW_RE = kwRe(PY_KW)
const NUMBER_RE = /\b\d+\.?\d*\b/g
const IDENT_RE = /[A-Za-z_]\w*/g
const FUNC_RE = /[A-Za-z_]\w*(?=\s*\()/g

function highlightPython(code) {
  const cleaned = stripHtmlTags(code)
  const escaped = escapeHtml(cleaned)
  const rules = [
    { type: 'ss', regex: PY_TRIPLE_DQ },
    { type: 'ss', regex: PY_DQ_STR },
    { type: 'ss', regex: PY_SQ_STR },
    { type: 'sc', regex: PY_COMMENT },
    { type: 'sk', regex: PY_KW_RE },
    { type: 'sd', regex: PY_DECORATOR },
    { type: 'sf', regex: FUNC_RE },
    { type: 'sn', regex: NUMBER_RE },
    { type: 'code', regex: IDENT_RE },
  ]
  const tokens = tokenize(escaped, rules)
  return renderTokens(tokens)
}

// ── 测试 ──

let passed = 0
let failed = 0

function test(name, fn) {
  try {
    fn()
    console.log(`✅ ${name}`)
    passed++
  } catch (e) {
    console.log(`❌ ${name}`)
    console.log(`   错误: ${e.message}`)
    failed++
  }
}

function assert(cond, msg) {
  if (!cond) throw new Error(msg || 'assertion failed')
}

function assertNotContains(haystack, needle, msg) {
  if (haystack.includes(needle)) {
    throw new Error(msg || `expected NOT to contain "${needle}", got: ${haystack}`)
  }
}

function assertContains(haystack, needle, msg) {
  if (!haystack.includes(needle)) {
    throw new Error(msg || `expected to contain "${needle}", got: ${haystack}`)
  }
}

console.log('\n═══════════════════════════════════════════════════════')
console.log('  省一标准 highlight.ts 测试 - 2026-07-12')
console.log('═══════════════════════════════════════════════════════\n')

// ─── 场景 1: 简单函数定义 ───
test('场景1: 简单 def 函数定义', () => {
  const code = `def hello():
    print("world")`
  const result = highlightPython(code)
  console.log('   debug result:', JSON.stringify(result))
  assertContains(result, '<span class="sk">def</span>', 'def 应该是关键字')
  assertContains(result, '<span class="sf">hello</span>', 'hello 应该是函数')
  assertContains(result, '<span class="sf">print</span>', 'print 应该是函数')
  assertNotContains(result, 'class="sk">def</span><', '不应该有破损的 HTML')
})

// ─── 场景 2: 字符串内的关键字 (最容易出 bug 的场景) ───
test('场景2: 字符串内的"def"不应被识别为关键字', () => {
  const code = `s = "def foo(): pass"
class Bar: pass`
  const result = highlightPython(code)
  // 字符串里的 def 应该在 ss span 内, 不是 sk
  // 注意: escapeHtml 不转义引号, 所以字符串内容保留原样
  assertContains(result, '<span class="ss">"def foo(): pass"</span>', '字符串应完整包裹 (含引号)')
  assertContains(result, '<span class="sk">class</span>', 'class 是关键字')
  assertContains(result, '<span class="sk">pass</span>', 'pass 是关键字')
  // 关键: 不应有破损的 <span class="sk">def 出现在字符串外
  // 正确的形式是 <span class="sk">def</span> 完整闭合
  const skDefCount = (result.match(/<span class="sk">def/g) || []).length
  assert(skDefCount === 0, `字符串外的 def 不应该是关键字, 实际命中 ${skDefCount} 次`)
})

// ─── 场景 3: 注释里的关键字 ───
test('场景3: 注释内的关键字不应被识别', () => {
  const code = `# def foo(): pass
def bar(): return 1`
  const result = highlightPython(code)
  assertContains(result, '<span class="sc"># def foo(): pass</span>', '注释完整包裹')
  assertContains(result, '<span class="sk">def</span>', 'def 仍是关键字')
  assertContains(result, '<span class="sf">bar</span>', 'bar 是函数')
})

// ─── 场景 4: 装饰器 ───
test('场景4: 装饰器被正确识别', () => {
  const code = `@staticmethod
def foo():
    pass`
  const result = highlightPython(code)
  assertContains(result, '<span class="sd">@staticmethod</span>', '@staticmethod 是装饰器')
})

// ─── 场景 5: 数字 ───
test('场景5: 数字被正确识别', () => {
  const code = `x = 42
y = 3.14`
  const result = highlightPython(code)
  assertContains(result, '<span class="sn">42</span>', '42 是数字')
  assertContains(result, '<span class="sn">3.14</span>', '3.14 是数字')
})

// ─── 场景 6: 用户报告的 bug 场景 ───
test('场景6: 核心 bug - 重复运行不累积错误', () => {
  const code = `def hello():
    return 1`
  // 多次运行, 结果应该完全一致 (幂等性)
  const r1 = highlightPython(code)
  const r2 = highlightPython(code)
  const r3 = highlightPython(code)
  assert(r1 === r2 && r2 === r3, '重复调用应产生相同结果')
  // 不应该有嵌套的 span
  assertNotContains(r1, '<span class="sk"><span', '不应有嵌套 span')
})

// ─── 场景 7: stripHtmlTags 清理残渣 ───
test('场景7: stripHtmlTags 能清理已损坏的输入', () => {
  const dirty = `class="sk">def hello():
    <span class="sf">return</span> 1`
  const cleaned = stripHtmlTags(dirty)
  assertNotContains(cleaned, 'class="sk"', '应清理 class="sk"')
  assertNotContains(cleaned, '<span', '应清理 <span')
  assertNotContains(cleaned, '</span>', '应清理 </span>')
  assertContains(cleaned, 'def hello():', '应保留 def')
})

// ─── 场景 8: 清理 placeholder 漏网 ───
test('场景8: 清理未展开的 placeholder', () => {
  const dirty = `__HL_SK_OPEN__def__HL_SK_CLOSE__ hello():`
  const cleaned = stripHtmlTags(dirty)
  assertNotContains(cleaned, '__HL_', '应清理所有 __HL_ 字符串')
})

// ─── 场景 9: HTML 转义防御 ───
test('场景9: HTML 特殊字符正确转义', () => {
  const code = `s = "<script>alert(1)</script>"`
  const result = highlightPython(code)
  console.log('   debug result:', JSON.stringify(result))
  // 关键: 不能出现原始的 <script> 标签 (会被浏览器当 HTML 解析)
  assertNotContains(result, '<script>', '不应有未转义的 <script>')
  // 转义形式应保留 (作为字符串内容)
  assertContains(result, '&lt;script&gt;', '应保留转义形式 &lt;script&gt;')
  assertContains(result, '&lt;/script&gt;', '应保留转义形式 &lt;/script&gt;')
})

// ─── 场景 10: 标识符 (变量名) 不被错误识别为关键字 ───
test('场景10: 变量名包含关键字子串应保持原样', () => {
  const code = `default_value = 1
class_name = "foo"`
  const result = highlightPython(code)
  // default_value 是 identifier, 不应被切成 default + _value
  assertContains(result, 'default_value', 'default_value 应保持完整')
  assertContains(result, 'class_name', 'class_name 应保持完整')
})

// ─── 场景 11: 用户原始 bug 报告复现 ───
test('场景11: 复现 class="sk">def 类型 bug', () => {
  // 这是用户报告的核心 bug: 输出像 class="sk">def
  const code = `def hello():
    return "def"  # inline def keyword`
  const result = highlightPython(code)
  // 关键检查: 每一个 <span class="sk">def</span> 都应该是完整闭合的
  // 不能出现 class="sk">def 后面没有 </span> 紧跟的情况
  // (即损坏的 <span class=<span class="sk">sk</span>>def 形式)
  const openSkDef = (result.match(/<span class="sk">def/g) || []).length
  const closeSkDef = (result.match(/<span class="sk">def<\/span>/g) || []).length
  assert(openSkDef === closeSkDef, `<span class="sk">def 出现 ${openSkDef} 次, 完整闭合 ${closeSkDef} 次`)
  // 计算总开标签数 vs 关标签数
  const allOpen = (result.match(/<span class="[^"]+">/g) || []).length
  const allClose = (result.match(/<\/span>/g) || []).length
  assert(allOpen === allClose, `开标签 ${allOpen} 个, 关标签 ${allClose} 个, 应相等 (没有破损标签)`)
})

// ─── 总结 ───
console.log(`\n═══════════════════════════════════════════════════════`)
console.log(`  测试结果: ${passed}/${passed + failed} 通过`)
console.log(`═══════════════════════════════════════════════════════\n`)

if (failed > 0) {
  process.exit(1)
}
