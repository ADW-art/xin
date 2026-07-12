/*
  SVG/PNG 导出工具

  用法:
    import { svgToPngDownload, svgElementToPngDownload } from '@/utils/export'

    // 从 SVG 字符串导出
    svgToPngDownload(svgString, 'mindmap.png')

    // 从 DOM 元素导出
    svgElementToPngDownload(document.querySelector('.mermaid svg'), 'diagram.png')
*/

export function svgToPngDownload(svgText: string, filename: string): void {
  const blob = new Blob([svgText], { type: 'image/svg+xml;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const img = new Image()
  img.onload = () => {
    const canvas = document.createElement('canvas')
    canvas.width = img.width * 2
    canvas.height = img.height * 2
    const ctx = canvas.getContext('2d')!
    ctx.scale(2, 2)
    ctx.fillStyle = '#FFFFFF'
    ctx.fillRect(0, 0, canvas.width, canvas.height)
    ctx.drawImage(img, 0, 0)
    URL.revokeObjectURL(url)
    canvas.toBlob((b) => {
      if (!b) return
      downloadBlob(b, filename)
    }, 'image/png')
  }
  img.src = url
}

export function svgElementToPngDownload(svgEl: SVGElement | null, filename: string): void {
  if (!svgEl) return
  const clone = svgEl.cloneNode(true) as SVGElement
  // Ensure viewBox is present for proper scaling
  const bbox = svgEl.getBoundingClientRect()
  if (!clone.getAttribute('viewBox')) {
    clone.setAttribute('viewBox', `0 0 ${bbox.width} ${bbox.height}`)
  }
  clone.setAttribute('width', String(Math.ceil(bbox.width)))
  clone.setAttribute('height', String(Math.ceil(bbox.height)))
  const svgText = new XMLSerializer().serializeToString(clone)
  svgToPngDownload(svgText, filename)
}

function downloadBlob(blob: Blob, filename: string): void {
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = filename
  document.body.appendChild(a)
  a.click()
  setTimeout(() => {
    document.body.removeChild(a)
    URL.revokeObjectURL(a.href)
  }, 100)
}
