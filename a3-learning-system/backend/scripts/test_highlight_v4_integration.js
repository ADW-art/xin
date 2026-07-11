// 完整测试: 模拟浏览器中的 highlightCode 调用
// 直接复制 highlight.ts 的核心算法, 确保逻辑一致

// ═══ 复制 highlight.ts 核心代码 ═══

function escapeHtml(str) {
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
}

function stripHtmlTags(code) {
  // 重要: 只剥离 <span> 标签 (这些一定是上一次高亮的残渣)
  // 不要剥离 <div> <code> <pre> 等 - 因为用户可能就是要高亮 HTML 代码!
  return code
    .replace(/<span\b[^>]*>/gi, '')
    .replace(/<\/span>/gi, '')
    .replace(/&lt;span\b[^&]*&gt;/gi, '')
    .replace(/&lt;\/span&gt;/gi, '')
    .replace(/"(?:sk|ss|sc|sn|sf|sd|hl|k|n|s|f|d|c|o|p|w|kc|kp)">/gi, '')
    .replace(/\s*class\s*=\s*"(?:sk|ss|sc|sn|sf|sd)[^"]*"/gi, '')
    .replace(/__HL_[A-Z]{2,3}_(?:OPEN|CLOSE)__/g, '')
}

function renderTokens(tokens) {
  const parts = []
  for (const tok of tokens) {
    if (tok.type === 'code') {
      // code 类型 token 来自已转义输入, 直接输出
      parts.push(tok.text)
    } else {
      parts.push(`<span class="${tok.type}">${tok.text}</span>`)
    }
  }
  return parts.join('')
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
        if (m) next = Math.min(next, m.index)
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

const PY_KW = new Set(['False','None','True','and','as','assert','async','await','break','class','continue','def','del','elif','else','except','finally','for','from','global','if','import','in','is','lambda','nonlocal','not','or','pass','raise','return','try','while','with','yield'])
const JS_KW = new Set(['break','case','catch','class','const','continue','debugger','default','delete','do','else','export','extends','finally','for','function','if','import','in','instanceof','let','new','return','super','switch','this','throw','try','typeof','var','void','while','with','yield','async','await','from','of','static','enum','interface','type','implements'])
const BASH_KW = new Set(['echo','cd','ls','cp','mv','rm','mkdir','git','npm','pip','python','node','docker','curl','wget','export','source','chmod','cat','grep','find','sed','awk','tar','ssh','scp','sudo','apt','brew','yarn','pnpm','npx','uvicorn','docker-compose','ps','kill'])
const SQL_KW = new Set(['SELECT','FROM','WHERE','INSERT','INTO','VALUES','UPDATE','SET','DELETE','CREATE','TABLE','ALTER','DROP','INDEX','JOIN','INNER','LEFT','RIGHT','OUTER','ON','AS','AND','OR','NOT','NULL','IS','LIKE','BETWEEN','IN','ORDER','BY','GROUP','HAVING','LIMIT','OFFSET','COUNT','SUM','AVG','MAX','MIN','DISTINCT','PRIMARY','KEY','FOREIGN','REFERENCES','INT','VARCHAR','TEXT','BOOLEAN','DATETIME','JSON'])
const CPP_KW = new Set(['int','float','double','char','void','bool','class','struct','namespace','using','template','typename','virtual','override','public','private','protected','const','static','auto','return','if','else','for','while','do','switch','case','break','continue','new','delete','nullptr','true','false','include','define','typedef','sizeof','try','catch','throw','std','cout','cin','endl','vector','string','map','set','pair','unique_ptr','shared_ptr','constexpr','noexcept','enum','explicit','friend','inline','long','short','signed','unsigned','union','volatile','wchar_t'])
const JAVA_KW = new Set(['public','private','protected','class','interface','extends','implements','static','final','void','int','long','double','float','boolean','char','String','return','if','else','for','while','do','switch','case','break','continue','new','this','super','try','catch','throw','throws','import','package','null','true','false','abstract','synchronized','volatile','transient','enum','instanceof','native','strictfp','assert','default'])
const GO_KW = new Set(['func','var','const','type','struct','interface','map','chan','defer','go','return','if','else','for','range','switch','case','break','continue','fallthrough','import','package','nil','true','false','make','new','append','len','cap','select','goto','int','int8','int16','int32','int64','uint','uint8','uint16','uint32','uint64','float32','float64','string','bool','byte','rune','error'])
const RUST_KW = new Set(['fn','let','mut','struct','impl','trait','enum','match','use','mod','pub','self','super','where','as','ref','loop','while','for','if','else','return','break','continue','in','move','async','await','Some','None','Ok','Err','Result','Option','Vec','String','const','static','type','dyn','unsafe','extern','crate','macro_rules','true','false','box','drop'])

function kwRe(set) {
  return new RegExp(`(?:${Array.from(set).join('|')})\\b`, 'g')
}

const PY_KW_RE = kwRe(PY_KW)
const JS_KW_RE = kwRe(JS_KW)
const BASH_KW_RE = kwRe(BASH_KW)
const SQL_KW_RE = kwRe(SQL_KW)
const CPP_KW_RE = kwRe(CPP_KW)
const JAVA_KW_RE = kwRe(JAVA_KW)
const GO_KW_RE = kwRe(GO_KW)
const RUST_KW_RE = kwRe(RUST_KW)

const NUMBER_RE = /\b\d+\.?\d*\b/g
const IDENT_RE = /[A-Za-z_]\w*/g
const FUNC_RE = /[A-Za-z_]\w*(?=\s*\()/g
const PY_TRIPLE_DQ = /"""[\s\S]*?"""/g
const PY_TRIPLE_SQ = /'''[\s\S]*?'''/g
const PY_DQ_STR = /"(?:[^"\\]|\\.)*"/g
const PY_SQ_STR = /'(?:[^'\\]|\\.)*'/g
const PY_COMMENT = /#[^\n]*/g
const PY_DECORATOR = /@\w+/g
const JS_DQ_STR = /"(?:[^"\\]|\\.)*"/g
const JS_SQ_STR = /'(?:[^'\\]|\\.)*'/g
const JS_TPL_STR = /`(?:[^`\\]|\\.)*`/g
const JS_LINE_COMMENT = /\/\/[^\n]*/g
const JS_BLOCK_COMMENT = /\/\*[\s\S]*?\*\//g
const SQL_STR = /'(?:[^'\\]|\\.)*'/g
const SQL_NUM = /\b\d+\.?\d*\b/g
const JSON_KEY = /"(?:[^"\\]|\\.)*"(?=\s*:)/g
const JSON_STR = /"(?:[^"\\]|\\.)*"/g
const JSON_LIT = /(?:true|false|null)\b/g
const HTML_TAG_NAME = /&lt;\/?[\w-]+/g
const HTML_ATTR = /[\w-]+(?==)/g
const HTML_COMMENT = /&lt;!--[\s\S]*?--&gt;/g
const CSS_BLOCK_COMMENT = /\/\*[\s\S]*?\*\//g
const CSS_SELECTOR = /[.#@][\w-]+/g
const CSS_PROP = /:\s*[\w-]+/g
const CSS_VALUE = /"(?:[^"\\]|\\.)*"/g
const CSS_NUM = /\b\d+\.?\d*(?:px|em|rem|%|vh|vw|s|ms)?\b/g
const YAML_COMMENT = /#[^\n]*/g
const YAML_KEY = /\s[\w-]+(?=\s*:)/g

// ── 主导出函数 ──
function highlightCode(code, lang) {
  let cleaned = stripHtmlTags(code)
  let escaped = escapeHtml(cleaned)
  if (!lang || lang === 'text' || lang === 'plaintext' || lang === 'plain') {
    return escaped
  }
  const l = lang.toLowerCase()
  let rules
  if (l === 'python' || l === 'py') {
    rules = [
      { type: 'ss', regex: PY_TRIPLE_DQ },
      { type: 'ss', regex: PY_TRIPLE_SQ },
      { type: 'ss', regex: PY_DQ_STR },
      { type: 'ss', regex: PY_SQ_STR },
      { type: 'sc', regex: PY_COMMENT },
      { type: 'sk', regex: PY_KW_RE },
      { type: 'sd', regex: PY_DECORATOR },
      { type: 'sf', regex: FUNC_RE },
      { type: 'sn', regex: NUMBER_RE },
      { type: 'code', regex: IDENT_RE },
    ]
  } else if (l === 'javascript' || l === 'js' || l === 'typescript' || l === 'ts') {
    rules = [
      { type: 'sc', regex: JS_BLOCK_COMMENT },
      { type: 'sc', regex: JS_LINE_COMMENT },
      { type: 'ss', regex: JS_TPL_STR },
      { type: 'ss', regex: JS_DQ_STR },
      { type: 'ss', regex: JS_SQ_STR },
      { type: 'sk', regex: JS_KW_RE },
      { type: 'sf', regex: FUNC_RE },
      { type: 'sn', regex: NUMBER_RE },
      { type: 'code', regex: IDENT_RE },
    ]
  } else if (l === 'sql') {
    rules = [
      { type: 'ss', regex: SQL_STR },
      { type: 'sk', regex: SQL_KW_RE },
      { type: 'sn', regex: SQL_NUM },
      { type: 'code', regex: IDENT_RE },
    ]
  } else if (l === 'json') {
    rules = [
      { type: 'sk', regex: JSON_KEY },
      { type: 'ss', regex: JSON_STR },
      { type: 'sk', regex: JSON_LIT },
      { type: 'sn', regex: NUMBER_RE },
      { type: 'code', regex: IDENT_RE },
    ]
  } else if (l === 'html' || l === 'xml' || l === 'svg') {
    rules = [
      { type: 'sk', regex: HTML_TAG_NAME },
      { type: 'sf', regex: HTML_ATTR },
      { type: 'ss', regex: JS_DQ_STR },
      { type: 'sc', regex: HTML_COMMENT },
      { type: 'code', regex: IDENT_RE },
    ]
  } else {
    return escaped
  }
  const tokens = tokenize(escaped, rules)
  return renderTokens(tokens)
}

// ═══ 全面集成测试 ═══

let passed = 0
let failed = 0
function test(name, fn) {
  try {
    fn()
    console.log(`✅ ${name}`)
    passed++
  } catch (e) {
    console.log(`❌ ${name}`)
    console.log(`   ${e.message}`)
    failed++
  }
}
function assert(c, m) { if (!c) throw new Error(m || 'fail') }
function assertContains(h, n, m) { if (!h.includes(n)) throw new Error(m || `expected contains "${n}", got: ${h.slice(0, 100)}`) }
function assertNotContains(h, n, m) { if (h.includes(n)) throw new Error(m || `expected NOT contains "${n}", got: ${h.slice(0, 100)}`) }

console.log('\n═══════════════════════════════════════════════════════')
console.log('  highlight.ts 全语言集成测试 - 2026-07-12')
console.log('═══════════════════════════════════════════════════════\n')

// ── Python ──
test('Python: def/class/字符串不冲突', () => {
  const r = highlightCode(`def foo():
    """这是文档字符串"""
    s = "def keyword in string"
    return 1`, 'python')
  assertContains(r, '<span class="sk">def</span>', 'def 是关键字')
  assertContains(r, '<span class="ss">"""这是文档字符串"""</span>', '文档字符串')
  assertContains(r, '<span class="ss">"def keyword in string"</span>', '字符串内 def 不应是关键字')
  // 检查 span 配对
  const opens = (r.match(/<span/g) || []).length
  const closes = (r.match(/<\/span>/g) || []).length
  assert(opens === closes, `span 不平衡: ${opens} 开 vs ${closes} 关`)
})

// ── JavaScript ──
test('JavaScript: function/var/箭头函数', () => {
  const r = highlightCode(`function hello() {
  const x = 42;
  return \`value is \${x}\`;
}`, 'javascript')
  assertContains(r, '<span class="sk">function</span>', 'function 关键字')
  assertContains(r, '<span class="sk">const</span>', 'const 关键字')
  assertContains(r, '<span class="sf">hello</span>', 'hello 是函数')
  assertContains(r, '<span class="sn">42</span>', '42 是数字')
  assertContains(r, '<span class="ss">`value is ${x}`</span>', '模板字符串')
})

// ── SQL ──
test('SQL: SELECT/FROM/WHERE', () => {
  const r = highlightCode(`SELECT id, name FROM users WHERE age > 18;`, 'sql')
  assertContains(r, '<span class="sk">SELECT</span>')
  assertContains(r, '<span class="sk">FROM</span>')
  assertContains(r, '<span class="sk">WHERE</span>')
  assertContains(r, '<span class="sn">18</span>')
})

// ── JSON ──
test('JSON: 键/值/字面量', () => {
  const r = highlightCode(`{"name": "test", "age": 42, "active": true}`, 'json')
  assertContains(r, '<span class="sk">"name"</span>', 'JSON key')
  assertContains(r, '<span class="ss">"test"</span>', 'JSON string value')
  assertContains(r, '<span class="sn">42</span>', 'JSON number')
  assertContains(r, '<span class="sk">true</span>', 'JSON literal')
})

// ── HTML ──
test('HTML: 标签/属性/字符串', () => {
  const r = highlightCode(`<div class="container" id="main">Hello</div>`, 'html')
  console.log('   debug HTML:', JSON.stringify(r))
  assertContains(r, '<span class="sk">&lt;div</span>', 'div 标签应转义后高亮')
  assertContains(r, '<span class="sf">class</span>', 'class 属性应高亮')
  assertContains(r, '<span class="ss">"container"</span>', '属性值应高亮')
  // 关键: span 数应该平衡
  const opens = (r.match(/<span/g) || []).length
  const closes = (r.match(/<\/span>/g) || []).length
  assert(opens === closes, `HTML span 不平衡: ${opens} vs ${closes}`)
})

// ── 重点: 用户原始 bug 场景 ──
test('用户原始 bug: 代码块出现 sk/sf 前缀', () => {
  // 用户报告: 输出像 class="sk">def
  // 我们的修复: 单遍分词, 不会有破损的 span
  const r = highlightCode(`class Foo:
    def bar(self):
        return "hello"`, 'python')
  // 关键: 不能有破损的 span (开标签多于关标签)
  const opens = (r.match(/<span/g) || []).length
  const closes = (r.match(/<\/span>/g) || []).length
  assert(opens === closes, `破损 bug 复现! ${opens} 开 vs ${closes} 关\n  result: ${r}`)
  assert(opens > 0, '应该至少有一些 span (说明高亮生效)')
})

// ── 压力测试: 长代码 ──
test('压力: 100 行 Python 代码', () => {
  const lines = []
  for (let i = 0; i < 100; i++) {
    lines.push(`def func_${i}():
    """docstring for func ${i}"""
    x = ${i}
    return x * 2`)
  }
  const code = lines.join('\n')
  const t0 = Date.now()
  const r = highlightCode(code, 'python')
  const ms = Date.now() - t0
  console.log(`   ⏱️  ${ms}ms, ${r.length} chars`)
  assert(ms < 1000, `100 行代码应在 1s 内完成, 实际 ${ms}ms`)
  const opens = (r.match(/<span/g) || []).length
  const closes = (r.match(/<\/span>/g) || []).length
  assert(opens === closes, `100 行代码 span 不平衡: ${opens} vs ${closes}`)
})

// ── 防御性测试: 损坏输入 ──
test('防御: 包含已损坏 span 的输入', () => {
  const dirty = `def <span class="sk">foo</span>():
    pass`
  const r = highlightCode(dirty, 'python')
  // stripHtmlTags 应该清理掉原始的 span
  // 然后 highlight 重新生成正确的 span
  // 结果不应包含双重 span
  assertNotContains(r, '<span class="sk"><span', '不应有嵌套 span')
  assertNotContains(r, '</span></span>', '不应有双重闭合')
})

// ── 总结 ──
console.log(`\n═══════════════════════════════════════════════════════`)
console.log(`  集成测试结果: ${passed}/${passed + failed} 通过`)
console.log(`═══════════════════════════════════════════════════════\n`)
if (failed > 0) process.exit(1)
