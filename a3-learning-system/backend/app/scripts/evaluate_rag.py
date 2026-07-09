"""
RAG 评测脚本 —— 匹配 C/算法/数据结构教材

评测集：20 道题，匹配 6 本入库教材
"""

import sys, json, time
from pathlib import Path

sys.path.insert(0, ".")

from app.services.rag_service import hybrid_search
from app.services.spark_client import SparkClient
from app.dependencies import get_spark_client

# 评测集——全部匹配 C Primer Plus、算法图解、啊哈算法、具体数学
TEST_SET = [
    {"id": 1, "question": "C语言中指针是什么，如何使用", "keywords": ["指针", "地址", "malloc", "&"], "source": "C Primer Plus"},
    {"id": 2, "question": "C语言的数组和指针有什么关系", "keywords": ["数组", "指针", "下标", "偏移"], "source": "C Primer Plus"},
    {"id": 3, "question": "C语言中结构体如何定义和使用", "keywords": ["struct", "结构体", "成员"], "source": "C Primer Plus"},
    {"id": 4, "question": "二分查找算法的原理是什么", "keywords": ["二分", "查找", "有序", "log"], "source": "算法图解"},
    {"id": 5, "question": "快速排序算法的基本思想和步骤", "keywords": ["快速排序", "partition", "分治", "递归"], "source": "算法图解"},
    {"id": 6, "question": "什么是广度优先搜索BFS", "keywords": ["广度优先", "BFS", "队列", "图"], "source": "算法图解"},
    {"id": 7, "question": "动态规划的基本思想是什么", "keywords": ["动态规划", "子问题", "重叠", "最优"], "source": "算法图解"},
    {"id": 8, "question": "C语言中函数如何定义和调用", "keywords": ["函数", "参数", "return", "声明"], "source": "C Primer Plus"},
    {"id": 9, "question": "什么是栈和队列，它们有什么区别", "keywords": ["栈", "队列", "FIFO", "LIFO"], "source": "大话数据结构"},
    {"id": 10, "question": "二叉树的遍历方式有哪几种", "keywords": ["二叉树", "遍历", "前序", "中序"], "source": "大话数据结构"},
    {"id": 11, "question": "C语言中内存如何动态分配", "keywords": ["malloc", "free", "堆", "动态"], "source": "C Primer Plus"},
    {"id": 12, "question": "什么是递归函数，递归的优缺点", "keywords": ["递归", "栈", "基准", "调用"], "source": "C Primer Plus"},
    {"id": 13, "question": "散列表（哈希表）的工作原理", "keywords": ["散列表", "哈希", "冲突", "键值"], "source": "算法图解"},
    {"id": 14, "question": "链表和数组有什么区别", "keywords": ["链表", "数组", "插入", "访问"], "source": "大话数据结构"},
    {"id": 15, "question": "什么是贪心算法", "keywords": ["贪心", "局部最优", "选择", "近似"], "source": "算法图解"},
    {"id": 16, "question": "C语言中文件读写操作的基本函数", "keywords": ["fopen", "fclose", "fread", "fwrite"], "source": "C Primer Plus"},
    {"id": 17, "question": "什么是Dijkstra算法", "keywords": ["Dijkstra", "最短路径", "加权图", "贪心"], "source": "算法图解"},
    {"id": 18, "question": "C语言中预处理指令有哪些", "keywords": ["#include", "#define", "宏", "条件编译"], "source": "C Primer Plus"},
    {"id": 19, "question": "冒泡排序和选择排序有什么区别", "keywords": ["冒泡", "选择", "比较", "交换"], "source": "啊哈算法"},
    {"id": 20, "question": "什么是堆数据结构", "keywords": ["堆", "完全二叉树", "优先队列"], "source": "大话数据结构"},
]


def evaluate_recall(results, keywords):
    content = " ".join(r["content"] for r in results)
    hits = sum(1 for kw in keywords if kw.lower() in content.lower())
    return hits / len(keywords) if keywords else 0


def evaluate_hallucination(answer, retrieved):
    if not answer or not retrieved:
        return 1.0
    answer_words = set(answer)
    retrieved_text = " ".join(r["content"] for r in retrieved)
    retrieved_words = set(retrieved_text)
    diff = answer_words - retrieved_words
    return len(diff) / len(answer_words) if answer_words else 1.0


def evaluate_answer_quality(answer, keywords):
    if not answer:
        return 0
    hits = sum(1 for kw in keywords if kw.lower() in answer.lower())
    return hits / len(keywords) if keywords else 0


def run_evaluation():
    print("=" * 60)
    print("RAG 评测报告——C/算法教材")
    print("=" * 60)

    spark = get_spark_client()
    metrics = {"recall": [], "precision": [], "accuracy": [], "hallucination": []}
    details = []

    for item in TEST_SET:
        print(f"\n[{item['id']}/20] {item['question']}")

        start = time.time()
        results = hybrid_search(item["question"], top_k=7, use_reranker=True)
        latency = round((time.time() - start) * 1000)

        recall = evaluate_recall(results, item["keywords"])
        precision = len([r for r in results if any(kw.lower() in r["content"].lower() for kw in item["keywords"])]) / max(len(results), 1)

        metrics["recall"].append(recall)
        metrics["precision"].append(precision)

        context = "\n\n".join(r["content"][:300] for r in results)
        prompt = f"根据以下教材内容回答问题。\n\n教材内容：\n{context}\n\n问题：{item['question']}\n\n回答（简洁，不超过100字）："
        try:
            answer = spark.chat_sync([{"role": "user", "content": prompt}], temperature=0.3, max_tokens=200)
        except Exception:
            answer = "生成失败"

        acc = evaluate_answer_quality(answer, item["keywords"])
        hall = evaluate_hallucination(answer, results)

        metrics["accuracy"].append(acc)
        metrics["hallucination"].append(hall)

        details.append({
            "id": item["id"], "question": item["question"],
            "recall": round(recall, 3), "precision": round(precision, 3),
            "accuracy": round(acc, 3), "hallucination": round(hall, 3),
            "latency_ms": latency, "result_count": len(results),
            "answer_preview": answer[:120],
        })

        print(f"  Recall={recall:.2f} Prec={precision:.2f} Acc={acc:.2f} Hall={hall:.2f} 延迟={latency}ms")

    avg_recall = sum(metrics["recall"]) / len(metrics["recall"])
    avg_precision = sum(metrics["precision"]) / len(metrics["precision"])
    avg_accuracy = sum(metrics["accuracy"]) / len(metrics["accuracy"])
    avg_hall = sum(metrics["hallucination"]) / len(metrics["hallucination"])

    print(f"\n{'='*60}")
    print("汇总结果")
    print(f"{'='*60}")
    print(f"  Recall:          {avg_recall:.3f}  (目标≥0.88)")
    print(f"  Precision:       {avg_precision:.3f}  (目标≥0.80)")
    print(f"  Accuracy:        {avg_accuracy:.3f}  (目标≥0.83)")
    print(f"  Hallucination:   {avg_hall:.3f}  (目标<0.09)")

    report = {
        "summary": {"recall": round(avg_recall, 3), "precision": round(avg_precision, 3), "accuracy": round(avg_accuracy, 3), "hallucination": round(avg_hall, 3)},
        "details": details,
    }
    report_path = Path(__file__).parent.parent.parent.parent / "docs" / "rag_evaluation_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\n评测报告已保存: {report_path}")


if __name__ == "__main__":
    run_evaluation()
