PROJ = a3-learning-system

.PHONY: help install test test-backend test-frontend lint build dev dev-backend dev-frontend deps check ci

help: ## 显示帮助
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ─── 安装 ───────────────────────────────────────────────
install: ## 安装所有依�?	cd $(PROJ)/backend && pip install -r requirements.txt
	cd $(PROJ)/frontend && npm install

# ─── 测试 ───────────────────────────────────────────────
test: test-backend test-frontend ## 跑全部测�?
test-backend: ## 跑后端测�?	cd $(PROJ)/backend && python -m pytest tests/ -v --tb=short

test-backend-coverage: ## 后端测试 + 覆盖�?	cd $(PROJ)/backend && python -m pytest tests/ --cov=app --cov-report=term --cov-report=html

test-frontend: ## 跑前端测�?	cd $(PROJ)/frontend && npm run test

# ─── 代码检�?───────────────────────────────────────────
lint: ## 代码检�?	cd $(PROJ)/backend && python -m ruff check app/ --quiet 2>NUL || echo "[lint] ruff 未安装或执行失败"
	cd $(PROJ)/frontend && npm run lint 2>NUL || echo "[lint] 前端 lint 未配�?

# ─── 构建 ───────────────────────────────────────────────
build: ## 构建前端
	cd $(PROJ)/frontend && npm run build

# ─── 开�?───────────────────────────────────────────────
deps: ## 启动基础设施 (Docker)
	cd $(PROJ) && docker-compose up -d mysql redis minio chromadb 2>NUL || echo "[deps] Docker 未安装或未运�?

dev-backend: ## 启动后端
	cd $(PROJ)/backend && uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload

dev-frontend: ## 启动前端
	cd $(PROJ)/frontend && npm run dev

dev: deps ## 一键启动开发环�?(deps + 提示)
	@echo "==> 基础设施已启�?(MySQL/Redis/MinIO/ChromaDB)"
	@echo "==> 在另一个终端运�? make dev-backend"
	@echo "==> 在另一个终端运�? make dev-frontend"

# ─── CI 完整管道 ──────────────────────────────────────
ci: lint test build ## CI 流水�? lint �?test �?build

check: ## 快速完整性检�?(不依赖外部服�?
	@echo "=== 项目结构检�?==="
	@test -d $(PROJ)/backend/app && echo "  [OK] 后端代码" || echo "  [FAIL] 缺少 backend/app"
	@test -d $(PROJ)/frontend/src && echo "  [OK] 前端代码" || echo "  [FAIL] 缺少 frontend/src"
	@test -f $(PROJ)/docker-compose.yml && echo "  [OK] docker-compose" || echo "  [FAIL] 缺少 docker-compose.yml"
	@echo "=== 环境检�?==="
	@python --version 2>NUL && echo "  [OK] Python" || echo "  [FAIL] Python 未安�?
	@node --version 2>NUL && echo "  [OK] Node.js" || echo "  [FAIL] Node.js 未安�?
	@echo "=== 检查完�?==="

# ─── 数据管道 ───────────────────────────────────────────────
ingest-all: ## 全量数据摄取
	cd $(PROJ)/backend && python run_ocr.py
	cd $(PROJ)/backend && python ingest_course.py
	cd $(PROJ)/backend && python ingest_knowledge_base.py

ingest-reset: ## 清除并重建数�?	cd $(PROJ)/backend && python rebuild_stores.py
	$(MAKE) ingest-all
