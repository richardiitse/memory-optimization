#!/usr/bin/env python3
"""
筛选 LongMemEval 中的 temporal-reasoning 问题

Usage:
    python3 scripts/filter_temporal_questions.py \
        --input data/longmemeval/longmemeval_oracle.json \
        --output /tmp/temporal_questions.json \
        --type temporal-reasoning
"""

import json
import argparse
from pathlib import Path


def filter_questions(input_path: str, output_path: str, question_type: str):
    """筛选指定类型的问题"""

    # 读取原始数据
    with open(input_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # 筛选指定类型
    filtered = [item for item in data if item['question_type'] == question_type]

    # 统计信息
    print(f"原始数据: {len(data)} 题")
    print(f"筛选类型: {question_type}")
    print(f"筛选结果: {len(filtered)} 题")

    # 分析时间跨度分布
    time_spans = []
    for item in filtered:
        if 'haystack_dates' in item and item['haystack_dates']:
            # 简单统计：haystack 中有多少个不同的日期
            dates = set([d.split()[0] for d in item['haystack_dates']])
            time_spans.append(len(dates))

    if time_spans:
        print(f"\n时间跨度分布（haystack 中不同日期数）:")
        print(f"  单日: {sum(1 for x in time_spans if x == 1)} 题")
        print(f"  多日: {sum(1 for x in time_spans if x > 1)} 题")
        print(f"  平均: {sum(time_spans) / len(time_spans):.1f} 个日期")

    # 保存结果
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(filtered, f, ensure_ascii=False, indent=2)

    print(f"\n已保存到: {output_path}")

    # 输出前 3 个问题示例
    print("\n问题示例:")
    for i, item in enumerate(filtered[:3], 1):
        print(f"\n{i}. {item['question']}")
        print(f"   答案: {item['answer']}")
        print(f"   日期: {item.get('question_date', 'N/A')}")


def main():
    parser = argparse.ArgumentParser(description='筛选 LongMemEval 问题')
    parser.add_argument('--input', required=True, help='输入 JSON 文件路径')
    parser.add_argument('--output', required=True, help='输出 JSON 文件路径')
    parser.add_argument('--type', default='temporal-reasoning', help='问题类型')

    args = parser.parse_args()

    filter_questions(args.input, args.output, args.type)


if __name__ == '__main__':
    main()
