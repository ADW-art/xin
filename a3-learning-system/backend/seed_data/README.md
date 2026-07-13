# 种子数据 (Seed Data)

本目录包含**开箱即用**的 Python 知识种子，让新人 clone 项目后**无需任何额外操作**即可体验完整的 RAG 检索。

## 📦 文件清单

| 文件 | 大小 | 说明 |
|---|---|---|
| `python_seed.jsonl.gz` | ~1.25 MB | 2496 条 Python 知识（已切分+向量化）|
| `VERSION.json` | < 1 KB | 生成元信息（版本/时间/依赖）|
| `README.md` | 本文件 | 说明 |

## 🎯 用途

- **新人 clone 后**：后端首次启动自动加载，立即可体验
- **演示场景**：老师验收/对外展示无需 30 分钟等待 ingest
- **CI/CD**：单元测试有稳定的数据基础

## 🔄 自动加载流程

```
1. 用户 git clone 仓库
2. 用户 docker-compose up -d      # 启动 MySQL/Redis/MinIO/ChromaDB
3. 用户 uvicorn app.main:app     # 启动后端
4. 后端启动钩子 → load_seed_data.py
5. 检测 knowledge_base 是否为空
   ├─ 空 → 加载 python_seed.jsonl.gz → 2496 条入库
   └─ 非空 → 跳过（用户已自己 ingest 过）
6. 启动完成，用户访问 http://localhost:5173 立即可用！
```

## 🔧 手动重载/导出

### 重新加载（强制覆盖）
```bash
cd backend
python scripts/load_seed_data.py --force
```

### 重新生成（主人本地用，不入仓）
```bash
# 1. 先跑一次 ingest 把知识图谱入库
python ingest_curated_kb.py

# 2. 导出当前 ChromaDB 中的 Python 部分
python scripts/export_python_seed.py

# 3. 提交到 git
git add backend/seed_data/
git commit -m "feat(seed): 刷新 Python 种子数据"
```

## ⚠️ 失效条件

以下情况需要**重新生成**种子数据：

1. **升级 BGE-M3 模型**（embedding 维度/精度可能变化）
2. **升级 ChromaDB 大版本**（如 0.5 → 0.6，存储格式可能不兼容）
3. **改进切分算法**（chunk_size 改变 → 检索结果不连续）
4. **主人想加新知识**（手动 ingest 后再 export）

## 📊 当前版本

参见 [VERSION.json](./VERSION.json)，包含：
- 生成时间
- ChromaDB 版本
- BGE-M3 模型标识
- 向量维度（1024）
- 重生成命令

## 🛡️ 体积优化

| 数据 | 原始 | gzip 后 | 入仓 |
|---|---|---|---|
| 40565 条全量 | ~937 MB | ~150 MB | ❌ |
| 2496 条 Python 精选 | ~10 MB | **1.25 MB** | ✅ |

**压缩率 87%**，几乎无感。

## 💡 设计原则

1. **小而精**：只放必要数据，不传派生中间产物
2. **可重建**：VERSION.json 明确重生方法，永不失效
3. **可降级**：加载失败不阻断主应用启动
4. **可覆盖**：用户自己 ingest 后种子不再生效
