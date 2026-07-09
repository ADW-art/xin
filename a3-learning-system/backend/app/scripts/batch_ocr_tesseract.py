"""
批量 OCR 扫描版 PDF → 提取文字 → 存为 .txt → 复用 batch_ingest_text 入库

用法:
  python app/scripts/batch_ocr_tesseract.py --books 5 --pages 40
  python app/scripts/batch_ocr_tesseract.py --books 3 --pages 60 --start-from 1
"""

import io, os, re, subprocess, sys, tempfile, time
from pathlib import Path

try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
except:
    pass

PDF_BASE = "E:/code/github_clone/pdf-计算机专业资源/Some-Many-Books/PDF-file"
MATERIALS_DIR = os.path.join(os.path.dirname(__file__), "knowledge_materials")
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "ocr_output")
DONE_FILE = os.path.join(os.path.dirname(__file__), "..", "..", "ocr_done.txt")
TESSERACT = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
PDF_DPI = 200

PRIORITY_OCR = [
        ("algorithms", "数据结构与算法分析：Java语言描述.pdf"),
        ("algorithms", "算法心得：高效算法的奥秘（第2版）.pdf"),
        ("algorithms", "算法设计与分析（第3版）.pdf"),
        ("algorithms", "编程之美：微软技术面试心得.pdf"),
        ("algorithms", "编程珠玑（第2版）.pdf"),
        ("c", "C专家编程.pdf"),
        ("c", "C语言接口与实现.pdf"),
        ("c", "C陷阱与缺陷.pdf"),
        ("c++", "C++ Primer Plus（第5版）.pdf"),
        ("c++", "C++编程思想（第1卷）.pdf"),
        ("clean-code", "编写可读代码的艺术.pdf"),
        ("clean-code", "领域驱动设计：软件核心复杂性应对之道.pdf"),
        ("computer-system", "深入理解计算机系统.pdf"),
        ("computer-system", "编码：隐匿在计算机软硬件背后的语言.pdf"),
        ("computer-system", "计算机程序的构造和解释（第2版）.pdf"),
        ("design-pattern", "设计模式之禅.pdf"),
        ("design-pattern", "设计模式：可复用面向对象软件的基础.pdf"),
        ("docker", "Docker容器与容器云（第2版）.pdf"),
        ("java", "Effective Java 中文版（第2版）.pdf"),
        ("java", "Java编程思想（第4版）.pdf"),
        ("javascript", "JavaScript_DOM编程艺术.pdf"),
        ("javascript", "JavaScript函数式编程.pdf"),
        ("javascript", "JavaScript权威指南(第6版).pdf"),
        ("javascript", "JavaScript设计模式.pdf"),
        ("javascript", "JavaScript设计模式与开发实践.pdf"),
        ("javascript", "JavaScript语言精粹.pdf"),
        ("javascript", "JavaScript高级程序设计(第3版).pdf"),
        ("javascript", "你不知道的JavaScript（上卷）.pdf"),
        ("javascript", "精通JavaScript.pdf"),
        ("linux", "Linux内核设计与实现（第三版）.pdf"),
        ("linux", "UNIX操作系统设计.pdf"),
        ("linux", "UNIX环境高级编程(第三版).pdf"),
        ("linux", "UNIX编程艺术.pdf"),
        ("linux", "UNIX网络编程卷2：进程间通信.pdf"),
        ("linux", "深入Linux内核架构.pdf"),
        ("linux", "深入理解linux内核（第三版）.pdf"),
        ("microservice", "微服务设计.pdf"),
        ("mongodb", "MongoDB权威指南.pdf"),
        ("mysql", "MySQL性能调优与架构设计.pdf"),
        ("mysql", "SQL基础教程.pdf"),
        ("mysql", "SQL学习指南.pdf"),
        ("nodejs", "Node即学即用.pdf"),
        ("nodejs", "Node学习指南.pdf"),
        ("nodejs", "了不起的Node.js.pdf"),
        ("others", "程序员修炼之道：从小工到专家.pdf"),
        ("others", "程序员的自我修养：链接、装载与库.pdf"),
        ("others", "高效程序员的45个习惯.pdf"),
        ("python", "Python基础教程（第2版）.pdf"),
        ("python", "Python源码剖析.pdf"),
        ("redis", "Redis入门指南（第2版）.pdf"),
        ("redis", "Redis实战.pdf"),
        ("redis", "Redis设计与实现.pdf"),
        ("system", "企业集成模式：设计、构建及部署消息传递解决方案.pdf"),
        ("system", "大型网站技术架构：核心原理与案例分析.pdf"),
        ("test", "测试驱动开发.pdf"),
        ("materials", "C++ 程序设计语言：第4部分 标准库（原书第4版 (Bjarne Stroustrup) (z-library.sk, 1lib.sk, z-lib.sk).pdf"),
        ("materials", "C++程序设计语言.第1～3部分.原书第4版 (Bjarne Stroustrup) (z-library.sk, 1lib.sk, z-lib.sk) (1).pdf"),
        ("materials", "C++程序设计语言.第1～3部分.原书第4版 (Bjarne Stroustrup) (z-library.sk, 1lib.sk, z-lib.sk) (2).pdf"),
        ("materials", "C++程序设计语言.第1～3部分.原书第4版 (Bjarne Stroustrup) (z-library.sk, 1lib.sk, z-lib.sk).pdf"),
        ("materials", "C程序设计（第五版）学习辅导 (谭浩强)（OCR） (谭浩强) (z-library.sk, 1lib.sk, z-lib.sk) (1).pdf"),
        ("materials", "C程序设计（第五版）学习辅导 (谭浩强)（OCR） (谭浩强) (z-library.sk, 1lib.sk, z-lib.sk).pdf"),
        ("materials", "C语言程序设计（第五版） (谭浩强) (z-library.sk, 1lib.sk, z-lib.sk).pdf"),
        ("materials", "GitHub入门与实践 (大塚弘记) (z-library.sk, 1lib.sk, z-lib.sk).pdf"),
        ("materials", "Java Web程序设计任务教程 (黑马程序员) (z-library.sk, 1lib.sk, z-lib.sk).pdf"),
        ("materials", "Java核心技术·卷 II（原书第11版）：高级特性 (凯 S.霍斯特曼 (Cay S.Horstmann)) (z-library.sk, 1lib.sk, z-lib.sk).pdf"),
        ("materials", "Java核心技术·卷 I（原书第11版） (凯·S.霍斯特曼 (Cay S. Horstmann)) (z-library.sk, 1lib.sk, z-lib.sk).pdf"),
        ("materials", "Python_深度学习实战：75个有关神经网络建模、强化学习与迁移 (Python_深度学习实战：75个有关神经网络建模、强化学习与迁移) (z-library.sk, 1lib.sk, z-lib.sk).pdf"),
        ("materials", "Python编程  从入门到实践 = Python Crash Course (Eric Matthes) (z-library.sk, 1lib.sk, z-lib.sk).pdf"),
        ("materials", "Python语言程序设计基础（第2版） (嵩天，礼欣，黄天羽 著) (z-library.sk, 1lib.sk, z-lib.sk).pdf"),
        ("materials", "Redis设计与实现 (黄健宏) (z-library.sk, 1lib.sk, z-lib.sk).pdf"),
        ("materials", "Rust 程序设计语言 简体中文版 (Steve Klabnik，Carol Nichols，Rust 中文社区译) (z-library.sk, 1lib.sk, z-lib.sk).pdf"),
        ("materials", "Rust权威指南（社区翻译版） (Steve Klabnik, Carol Nichols etc.) (z-library.sk, 1lib.sk, z-lib.sk).pdf"),
        ("materials", "Spring实战（第5版）【文字版】 (克雷格·沃斯) (z-library.sk, 1lib.sk, z-lib.sk).pdf"),
        ("materials", "TCPIP详解 卷1：协议（原书第2版） (凯文 R. 福尔 (Kevin R. Fall) etc.) (z-library.sk, 1lib.sk, z-lib.sk).pdf"),
        ("materials", "[图灵程序设计丛书].Web安全开发指南 ([美] John Paul Mueller) (z-library.sk, 1lib.sk, z-lib.sk).pdf"),
        ("materials", "人工智能之知识图谱【文字版】 (主编, 李涓子, 刘佳, 编辑, 陶硕, 时嘉琪, 何杨, 唐丽杭 etc.) (z-library.sk, 1lib.sk, z-lib.sk).pdf"),
        ("materials", "人工智能导论 (李德毅, 于剑, 中国人工智能学会, 马少平, 王万良, 李绢子) (z-library.sk, 1lib.sk, z-lib.sk).pdf"),
        ("materials", "人工智能：一种现代的方法（第3版） (罗素 诺维格) (z-library.sk, 1lib.sk, z-lib.sk).pdf"),
        ("materials", "具体数学 计算机科学基础（第2版）.pdf"),
        ("materials", "内网渗透技术 (吴丽进 主编；苗春雨 主编；郑州 副主编；雷珊珊 副主编；王伦 副主编) (z-library.sk, 1lib.sk, z-lib.sk).pdf"),
        ("materials", "分布式系统：概念与设计（原书第五版） ( etc.) (z-library.sk, 1lib.sk, z-lib.sk).pdf"),
        ("materials", "动手学PyTorch建模与应用：从深度学习到大模型 (王国平) (z-library.sk, 1lib.sk, z-lib.sk).pdf"),
        ("materials", "动手学深度学习-PyTorch(第二版) (Aston Zhang, Zachary C. Lipton, 李沐 etc.) (z-library.sk, 1lib.sk, z-lib.sk).pdf"),
        ("materials", "啊哈!算法_.pdf"),
        ("materials", "图解HTTP (上野宣) (z-library.sk, 1lib.sk, z-lib.sk).pdf"),
        ("materials", "大数据技术原理与应用(第三版) (林子雨) (z-library.sk, 1lib.sk, z-lib.sk).pdf"),
        ("materials", "密码编码学与网络安全 原理与实践 第七版 ( etc.) (z-library.sk, 1lib.sk, z-lib.sk).pdf"),
        ("materials", "操作系统概念（原书第9版） ( etc.) (z-library.sk, 1lib.sk, z-lib.sk).pdf"),
        ("materials", "数据库系统概念 原书第6版 本科教学版 (Silberschatz，Korth，Sudarshan著 etc.) (z-library.sk, 1lib.sk, z-lib.sk).pdf"),
        ("materials", "数据库系统概论 (第5版) 习题解析与实验指导 (王珊, 张俊) (z-library.sk, 1lib.sk, z-lib.sk).pdf"),
        ("materials", "数据库系统概论（第5版） (王珊 萨师煊) (z-library.sk, 1lib.sk, z-lib.sk).pdf"),
        ("materials", "数据结构、算法与应用（原书第2版） C++语言描述 (Sartaj Sahni) (z-library.sk, 1lib.sk, z-lib.sk).pdf"),
        ("materials", "数据结构与算法分析 (Weiss, Mark Allen·韦斯,韦斯) (z-library.sk, 1lib.sk, z-lib.sk) (1).pdf"),
        ("materials", "数据结构与算法分析 (Weiss, Mark Allen·韦斯,韦斯) (z-library.sk, 1lib.sk, z-lib.sk).pdf"),
        ("materials", "数据结构与算法分析 C++语言描述.4th2016 (Mark Allen Weiss) (z-library.sk, 1lib.sk, z-lib.sk).pdf"),
        ("materials", "机器学习 (周志华) (z-library.sk, 1lib.sk, z-lib.sk).pdf"),
        ("materials", "机器学习导论（原书第3版） ([土耳其] 埃塞姆·阿培丁（EthemAlpaydin）) (z-library.sk, 1lib.sk, z-lib.sk)(1).pdf"),
        ("materials", "机器学习导论（原书第3版） ([土耳其] 埃塞姆·阿培丁（EthemAlpaydin）) (z-library.sk, 1lib.sk, z-lib.sk).pdf"),
        ("materials", "深入理解Nginx：模块开发与架构解析（第2版） (LinuxUnix技术丛书) (陶辉 著 [著, 陶辉]) (z-library.sk, 1lib.sk, z-lib.sk).pdf"),
        ("materials", "深入理解机器学习：从原理到算法 (Shai Shalev  Shwartz Shai Ben David) (z-library.sk, 1lib.sk, z-lib.sk).pdf"),
        ("materials", "深入理解计算机系统 (Randal E. Bryant, David R. O’Hallaron) (z-library.sk, 1lib.sk, z-lib.sk).pdf"),
        ("materials", "清华大学计算机系列教材 计算机操作系统教程 (张尧学 宋虹 张高) (z-library.sk, 1lib.sk, z-lib.sk).pdf"),
        ("materials", "现代操作系统 (Andrew S. Tanenbaum, Herbert Bos) (z-library.sk, 1lib.sk, z-lib.sk).pdf"),
        ("materials", "离散数学及其应用（原书第8版） (Kenneth H.Rosen) (z-library.sk, 1lib.sk, z-lib.sk).pdf"),
        ("materials", "算法基础.打开算法之门 (算法基础.打开算法之门) (z-library.sk, 1lib.sk, z-lib.sk).pdf"),
        ("materials", "算法导论（原书第3版） (Thomas H.Cormen,Charles E.Leiserson etc.) (z-library.sk, 1lib.sk, z-lib.sk).pdf"),
        ("materials", "线性代数 (同济大学数学系) (z-library.sk, 1lib.sk, z-lib.sk).pdf"),
        ("materials", "统计学习方法（第2版） (李航) (z-library.sk, 1lib.sk, z-lib.sk).pdf"),
        ("materials", "编译原理 第二版 (Alfred V. Aho,Monica S.Lam, Ravi Sethi etc.) (z-library.sk, 1lib.sk, z-lib.sk).pdf"),
        ("materials", "计算机操作系统（第四版） (汤小丹) (z-library.sk, 1lib.sk, z-lib.sk).pdf"),
        ("materials", "计算机科学丛书：编译原理（第2版） ([美]Alfred V.Aho, [美]Monica S.Lam etc.) (z-library.sk, 1lib.sk, z-lib.sk).pdf"),
        ("materials", "计算机程序设计艺术（第一卷）：基本算法 (计算机程序设计艺术（第一卷）：基本算法) (z-library.sk, 1lib.sk, z-lib.sk).pdf"),
        ("materials", "计算机系统：系统架构与操作系统的高度集成 (A MAI KEN SHANG ER LA MU A TA DE...) (z-library.sk, 1lib.sk, z-lib.sk).pdf"),
        ("materials", "计算机组成原理 (艾伦·克莱门茨 (Alan Clements)) (z-library.sk, 1lib.sk, z-lib.sk).pdf"),
        ("materials", "计算机网络 (谢希仁) (z-library.sk, 1lib.sk, z-lib.sk).pdf"),
        ("materials", "计算机网络（原书第7版） 自顶向下方法 (James F. Kurose Keith W. Ross) (z-library.sk, 1lib.sk, z-lib.sk)(1).pdf"),
        ("materials", "软件工程导论 (张海藩 牟永敏) (z-library.sk, 1lib.sk, z-lib.sk).pdf"),
        ("materials", "软件工程导论 (第6版) 学习辅导 (张海藩) (z-library.sk, 1lib.sk, z-lib.sk).pdf"),
        ("materials", "软件测试（原书第2版）(Software Testing, 2nd Edition) ([美] Ron Patton) (z-library.sk, 1lib.sk, z-lib.sk).pdf"),
        ("materials", "高等数学 同济第七版7版 上册 习题全解指南 课后习题答案解析.pdf"),
        ("materials", "高等数学·下册 第七版 (同济大学数学系) (z-library.sk, 1lib.sk, z-lib.sk).pdf"),
]


def ocr_page(page, page_num: int) -> str:
    """OCR a single page using Tesseract subprocess"""
    try:
        img = page.to_image(resolution=PDF_DPI)
        from PIL import Image
        import numpy as np
        pil_img = Image.fromarray(np.array(img.original))

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp_in:
            pil_img.save(tmp_in.name)

        out_base = tmp_in.name.replace(".png", "")
        subprocess.run(
            [TESSERACT, tmp_in.name, out_base, "-l", "chi_sim+eng", "--psm", "6"],
            capture_output=True, text=True, timeout=30,
        )
        os.unlink(tmp_in.name)

        out_file = out_base + ".txt"
        if os.path.exists(out_file):
            with open(out_file, "r", encoding="utf-8") as f:
                text = f.read().strip()
            os.unlink(out_file)
            return text
    except Exception as e:
        if page_num <= 2:
            print(f"    第{page_num}页 OCR失败: {e}")
    return ""


def clean_text(text: str) -> str:
    lines = []
    for line in text.split("\n"):
        line = line.strip()
        if not line or len(line) < 10:
            continue
        if re.match(r"^\s*\d{1,4}\s*$", line):
            continue
        if re.match(r"^[\s\-_=#*~·.•|/\\]+$", line):
            continue
        lines.append(line)
    return "\n".join(lines)


def ocr_book(subject: str, filename: str, path: str, max_pages: int) -> str:
    """OCR a book → save to txt, return filepath"""
    import pdfplumber
    title = filename.rsplit(".", 1)[0][:40]
    print(f"  OCR {max_pages} 页...")
    t0 = time.time()
    pages_text = []

    with pdfplumber.open(path) as pdf:
        total = len(pdf.pages)
        to_ocr = min(max_pages, total)
        for i in range(to_ocr):
            text = ocr_page(pdf.pages[i], i + 1)
            if text:
                pages_text.append(text)
            if (i + 1) % 10 == 0:
                pct = (i + 1) * 100 // to_ocr
                print(f"    {i+1}/{to_ocr} ({pct}%) {time.time()-t0:.0f}s")

    if not pages_text:
        print("  OCR 无结果")
        return ""

    full = clean_text("\n\n".join(pages_text))
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    out_name = f"{subject}__{title}.txt".replace("/", "_").replace(" ", "_")[:120]
    out_path = os.path.join(OUTPUT_DIR, out_name)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(full)
    elapsed = time.time() - t0
    print(f"  DONE: {len(full)} chars → {out_path} ({elapsed:.0f}s)")
    return out_path


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--books", type=int, default=3)
    parser.add_argument("--pages", type=int, default=40)
    parser.add_argument("--start-from", type=int, default=1)
    args = parser.parse_args()

    if not os.path.exists(TESSERACT):
        print(f"Tesseract 未找到: {TESSERACT}")
        print("请安装: https://github.com/UB-Mannheim/tesseract/wiki")
        sys.exit(1)

    already = set()
    if os.path.exists(DONE_FILE):
        with open(DONE_FILE, "r", encoding="utf-8") as f:
            already = set(line.strip() for line in f)

    todo = []
    for subj, fname in PRIORITY_OCR:
        key = f"{subj}/{fname}"
        if key in already:
            continue
        path = os.path.join(MATERIALS_DIR if subj == "materials" else PDF_BASE, subj, fname)
        if os.path.exists(path):
            todo.append((subj, fname, path, key))

    si = max(0, args.start_from - 1)
    ei = min(len(todo), si + args.books)
    batch = todo[si:ei]

    print(f"OCR {len(batch)}/{len(todo)} 本 (第{si+1}-{ei}本, 每本{args.pages}页)\n")

    ok = 0
    for i, (subj, fname, path, key) in enumerate(batch):
        print(f"[{si+i+1}/{len(todo)}] {subj}/{fname[:50]}")
        result = ocr_book(subj, fname, path, args.pages)
        if result:
            ok += 1
        with open(DONE_FILE, "a", encoding="utf-8") as f:
            f.write(key + "\n")

    print(f"\nDone: {ok}/{len(batch)} books OCR'd → {OUTPUT_DIR}")
    if ok > 0:
        print(f"Next: python app/scripts/batch_ingest_text.py (to ingest txt files)")
