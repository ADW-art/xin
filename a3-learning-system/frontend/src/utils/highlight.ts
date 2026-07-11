/*
  共享代码高亮工具 (shared syntax highlighting utility)

  作用：
    提供多语言代码语法高亮和 base64 编解码工具函数
    ChatMessage.vue 和 CodeCard.vue 共用此模块

  高亮方案：单遍扫描 + token 数组 (参考 highlight.js / prism.js 设计)
  - 不在源码上"就地修改", 而是把代码切分成 token 数组
  - 拼接时按 token 类型加 class, 彻底避免"正则匹配到 attribute 内部"的问题
  - 这种方式业界使用 10+ 年, 稳定性经得起考验
  覆盖语言：Python / JS/TS / Bash / SQL / JSON / HTML/XML / CSS/SCSS / YAML / C/C++ / Java / Go / Rust
*/

/* ── SVG icons ── */
export const SVG_COPY =
  '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>'
export const SVG_CHECK =
  '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>'

/* ── LRU cache ── */
const _hlCache = new Map<string, string>()
const HL_CACHE_MAX = 100

/* ── base64 编解码 (UTF-8 安全) ── */
export function safeBtoa(str: string): string {
  const bytes = new TextEncoder().encode(str)
  let binary = ''
  for (let i = 0; i < bytes.length; i++) {
    binary += String.fromCharCode(bytes[i])
  }
  return btoa(binary)
}

export function safeAtob(encoded: string): string {
  const binary = atob(encoded)
  const bytes = new Uint8Array(binary.length)
  for (let i = 0; i < binary.length; i++) {
    bytes[i] = binary.charCodeAt(i)
  }
  return new TextDecoder().decode(bytes)
}

/* ── HTML 清理：剥离 LLM 可能输出的语法高亮标签残渣 ── */
function stripHtmlTags(code: string): string {
  // 重要: 只剥离 <span> 标签 (这些一定是上一次高亮的残渣)
  // 不要剥离 <div> <code> <pre> 等 - 因为用户可能就是要高亮 HTML 代码!
  return code
    .replace(/<span\b[^>]*>/gi, '')
    .replace(/<\/span>/gi, '')
    .replace(/&lt;span\b[^&]*&gt;/gi, '')
    .replace(/&lt;\/span&gt;/gi, '')
    .replace(/"(?:sk|ss|sc|sn|sf|sd|hl|k|n|s|f|d|c|o|p|w|kc|kp)">/gi, '')
    .replace(/\s*class\s*=\s*"(?:sk|ss|sc|sn|sf|sd)[^"]*"/gi, '')
    // 防御性清理: 移除任何漏网的 placeholder 字符串
    .replace(/__HL_[A-Z]{2,3}_(?:OPEN|CLOSE)__/g, '')
}

/* ── HTML 转义 ── */
function escapeHtml(str: string): string {
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
}

/* ── Token 类型 + 输出函数 ── */
type Token = { type: 'code' | string; text: string }

/**
 * 把 token 数组拼接成带高亮 span 的 HTML 字符串
 * 这是整个高亮器的"输出阶段" - 唯一生成 HTML 标签的地方
 * 因为我们已经切分好, 不存在二次匹配问题
 *
 * 重要: 所有 token.text 都来自已经 escapeHtml 处理的输入
 * 不能再做 escape, 否则会导致双转义: &lt; 变成 &amp;lt;
 */
function renderTokens(tokens: Token[]): string {
  const parts: string[] = []
  for (const tok of tokens) {
    if (tok.type === 'code') {
      // code 类型 token 来自已转义输入, 直接输出
      parts.push(tok.text)
    } else {
      // 高亮 token: text 来自已转义输入, 直接包裹 span
      parts.push(`<span class="${tok.type}">${tok.text}</span>`)
    }
  }
  return parts.join('')
}

/* ═══════════════════════════════════════════════════════════
   单遍扫描分词器 (Single-pass tokenizer)
   对标 highlight.js: 用一个正则的 exec 循环扫描代码,
   每段根据"优先级最高的 token 类型"切分, 完全避免二次匹配
   ═══════════════════════════════════════════════════════════ */

interface TokenRule {
  type: string
  regex: RegExp
}

/**
 * 通用扫描器: 按规则优先级顺序切分代码
 * @param code - 已转义的 HTML 源码
 * @param rules - 规则列表, 顺序敏感 (前面的规则优先级高)
 * @returns token 数组
 */
function tokenize(code: string, rules: TokenRule[]): Token[] {
  const tokens: Token[] = []
  let pos = 0
  const n = code.length

  while (pos < n) {
    let matched = false

    for (const rule of rules) {
      // 必须从当前位置开始匹配
      rule.regex.lastIndex = pos
      const m = rule.regex.exec(code)
      if (m && m.index === pos) {
        // 命中
        tokens.push({ type: rule.type, text: m[0] })
        pos += m[0].length
        matched = true
        break
      }
    }

    if (!matched) {
      // 没有规则命中, 累积普通 code 段
      let next = pos + 1
      // 试探: 找到下一个能命中的位置
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
        // 兜底: 单字符
        tokens.push({ type: 'code', text: code[pos] })
        pos++
      }
    }
  }

  return tokens
}

/* ── 关键字集合 (按语言) ── */
const PY_KW = new Set([
  'False','None','True','and','as','assert','async','await','break','class','continue',
  'def','del','elif','else','except','finally','for','from','global','if','import',
  'in','is','lambda','nonlocal','not','or','pass','raise','return','try','while',
  'with','yield',
])
const JS_KW = new Set([
  'break','case','catch','class','const','continue','debugger','default','delete','do',
  'else','export','extends','finally','for','function','if','import','in','instanceof',
  'let','new','return','super','switch','this','throw','try','typeof','var','void',
  'while','with','yield','async','await','from','of','static','enum','interface','type',
  'implements',
])
const BASH_KW = new Set([
  'echo','cd','ls','cp','mv','rm','mkdir','git','npm','pip','python','node','docker',
  'curl','wget','export','source','chmod','cat','grep','find','sed','awk','tar','ssh',
  'scp','sudo','apt','brew','yarn','pnpm','npx','uvicorn','docker-compose','ps','kill',
])
const SQL_KW = new Set([
  'SELECT','FROM','WHERE','INSERT','INTO','VALUES','UPDATE','SET','DELETE','CREATE',
  'TABLE','ALTER','DROP','INDEX','JOIN','INNER','LEFT','RIGHT','OUTER','ON','AS','AND',
  'OR','NOT','NULL','IS','LIKE','BETWEEN','IN','ORDER','BY','GROUP','HAVING','LIMIT',
  'OFFSET','COUNT','SUM','AVG','MAX','MIN','DISTINCT','PRIMARY','KEY','FOREIGN',
  'REFERENCES','INT','VARCHAR','TEXT','BOOLEAN','DATETIME','JSON',
])
const CPP_KW = new Set([
  'int','float','double','char','void','bool','class','struct','namespace','using',
  'template','typename','virtual','override','public','private','protected','const',
  'static','auto','return','if','else','for','while','do','switch','case','break',
  'continue','new','delete','nullptr','true','false','include','define','typedef',
  'sizeof','try','catch','throw','std','cout','cin','endl','vector','string','map',
  'set','pair','unique_ptr','shared_ptr','constexpr','noexcept','enum','explicit',
  'friend','inline','long','short','signed','unsigned','union','volatile','wchar_t',
])
const JAVA_KW = new Set([
  'public','private','protected','class','interface','extends','implements','static',
  'final','void','int','long','double','float','boolean','char','String','return','if',
  'else','for','while','do','switch','case','break','continue','new','this','super',
  'try','catch','throw','throws','import','package','null','true','false','abstract',
  'synchronized','volatile','transient','enum','instanceof','native','strictfp','assert',
  'default',
])
const GO_KW = new Set([
  'func','var','const','type','struct','interface','map','chan','defer','go','return',
  'if','else','for','range','switch','case','break','continue','fallthrough','import',
  'package','nil','true','false','make','new','append','len','cap','select','goto',
  'int','int8','int16','int32','int64','uint','uint8','uint16','uint32','uint64',
  'float32','float64','string','bool','byte','rune','error',
])
const RUST_KW = new Set([
  'fn','let','mut','struct','impl','trait','enum','match','use','mod','pub','self',
  'super','where','as','ref','loop','while','for','if','else','return','break',
  'continue','in','move','async','await','Some','None','Ok','Err','Result','Option',
  'Vec','String','const','static','type','dyn','unsafe','extern','crate','macro_rules',
  'true','false','box','drop',
])

/* ── 构造"按位置匹配"的单 token 正则 ── */
// 必须用 /g 标志, 配合分词器的 lastIndex 机制实现"从任意 pos 开始匹配"
function kwRe(set: Set<string>): RegExp {
  // 不要用 ^ 锚点, 分词器通过 m.index === pos 判断匹配位置
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

/* ── 通用规则 (各语言共享) ── */
const NUMBER_RE = /\b\d+\.?\d*\b/g
const IDENT_RE = /[A-Za-z_]\w*/g
const FUNC_RE = /[A-Za-z_]\w*(?=\s*\()/g

/* ── 注释/字符串规则 (按语言) ── */
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
// 属性名不应包含前导空格 (空格留在 code token 里)
const HTML_ATTR = /[\w-]+(?==)/g
const HTML_COMMENT = /&lt;!--[\s\S]*?--&gt;/g

const CSS_BLOCK_COMMENT = /\/\*[\s\S]*?\*\//g
const CSS_SELECTOR = /[.#@][\w-]+/g
const CSS_PROP = /:\s*[\w-]+/g
const CSS_VALUE = /"(?:[^"\\]|\\.)*"/g
const CSS_NUM = /\b\d+\.?\d*(?:px|em|rem|%|vh|vw|s|ms)?\b/g

const YAML_COMMENT = /#[^\n]*/g
const YAML_KEY = /\s[\w-]+(?=\s*:)/g

/* ══════════════════════════════════════════════
   主导出函数
   ══════════════════════════════════════════════ */

export function highlightCode(code: string, lang?: string): string {
  const cacheKey = `${lang || 'text'}:${code.slice(0, 200)}`
  if (_hlCache.has(cacheKey)) return _hlCache.get(cacheKey)!

  let cleaned = stripHtmlTags(code)
  let escaped = escapeHtml(cleaned)

  if (!lang || lang === 'text' || lang === 'plaintext' || lang === 'plain') {
    _hlCache.set(cacheKey, escaped)
    return escaped
  }

  let rules: TokenRule[] = []
  const l = lang.toLowerCase()

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
  } else if (l === 'bash' || l === 'sh' || l === 'shell') {
    rules = [
      { type: 'sc', regex: PY_COMMENT },
      { type: 'ss', regex: PY_DQ_STR },
      { type: 'ss', regex: PY_SQ_STR },
      { type: 'sk', regex: BASH_KW_RE },
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
  } else if (l === 'css' || l === 'scss') {
    rules = [
      { type: 'sc', regex: CSS_BLOCK_COMMENT },
      { type: 'sk', regex: CSS_SELECTOR },
      { type: 'sf', regex: CSS_PROP },
      { type: 'ss', regex: CSS_VALUE },
      { type: 'sn', regex: CSS_NUM },
      { type: 'code', regex: IDENT_RE },
    ]
  } else if (l === 'yaml' || l === 'yml') {
    rules = [
      { type: 'sc', regex: YAML_COMMENT },
      { type: 'sk', regex: YAML_KEY },
      { type: 'ss', regex: JS_DQ_STR },
      { type: 'code', regex: IDENT_RE },
    ]
  } else if (l === 'cpp' || l === 'c++' || l === 'c') {
    rules = [
      { type: 'sc', regex: JS_BLOCK_COMMENT },
      { type: 'sc', regex: JS_LINE_COMMENT },
      { type: 'sc', regex: PY_COMMENT },
      { type: 'ss', regex: JS_DQ_STR },
      { type: 'sk', regex: CPP_KW_RE },
      { type: 'sf', regex: FUNC_RE },
      { type: 'sn', regex: NUMBER_RE },
      { type: 'code', regex: IDENT_RE },
    ]
  } else if (l === 'java') {
    rules = [
      { type: 'sc', regex: JS_BLOCK_COMMENT },
      { type: 'sc', regex: JS_LINE_COMMENT },
      { type: 'ss', regex: JS_DQ_STR },
      { type: 'ss', regex: JS_SQ_STR },
      { type: 'sk', regex: JAVA_KW_RE },
      { type: 'sf', regex: FUNC_RE },
      { type: 'sn', regex: NUMBER_RE },
      { type: 'code', regex: IDENT_RE },
    ]
  } else if (l === 'go' || l === 'golang') {
    rules = [
      { type: 'sc', regex: JS_LINE_COMMENT },
      { type: 'sc', regex: JS_BLOCK_COMMENT },
      { type: 'ss', regex: JS_TPL_STR },
      { type: 'ss', regex: JS_DQ_STR },
      { type: 'sk', regex: GO_KW_RE },
      { type: 'sf', regex: FUNC_RE },
      { type: 'sn', regex: NUMBER_RE },
      { type: 'code', regex: IDENT_RE },
    ]
  } else if (l === 'rust' || l === 'rs') {
    rules = [
      { type: 'sc', regex: JS_LINE_COMMENT },
      { type: 'sc', regex: JS_BLOCK_COMMENT },
      { type: 'ss', regex: JS_DQ_STR },
      { type: 'ss', regex: JS_SQ_STR },
      { type: 'sk', regex: RUST_KW_RE },
      { type: 'sf', regex: FUNC_RE },
      { type: 'sn', regex: /\b\d+\.?\d*(?:u8|u16|u32|u64|i8|i16|i32|i64|f32|f64|usize|isize)?\b/g },
      { type: 'code', regex: IDENT_RE },
    ]
  } else {
    // 未知语言: 只做转义, 不高亮
    _hlCache.set(cacheKey, escaped)
    return escaped
  }

  const tokens = tokenize(escaped, rules)
  const result = renderTokens(tokens)

  // LRU 淘汰
  if (_hlCache.size >= HL_CACHE_MAX) {
    const firstKey = _hlCache.keys().next().value
    if (firstKey) _hlCache.delete(firstKey)
  }
  _hlCache.set(cacheKey, result)

  return result
}
