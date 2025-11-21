#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
隐藏知识库日志分析脚本
用于分析隐藏知识库的检索和调用情况
"""
import os
import json
import datetime
from typing import Dict, List, Any
from collections import defaultdict, Counter


def load_json_logs(date_str: str = None) -> List[Dict]:
    """加载指定日期的 JSON 日志"""
    if date_str is None:
        date_str = datetime.datetime.now().strftime("%Y-%m-%d")
    
    json_file = f"logs/hidden_logs/hidden_kb_{date_str}.json"
    
    if not os.path.exists(json_file):
        print(f"❌ 日志文件不存在: {json_file}")
        return []
    
    logs = []
    try:
        with open(json_file, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    logs.append(json.loads(line))
    except Exception as e:
        print(f"❌ 读取日志文件失败: {e}")
        return []
    
    return logs


def analyze_daily_stats(logs: List[Dict]) -> Dict[str, Any]:
    """分析每日统计"""
    stats = {
        "总检索次数": 0,
        "成功检索次数": 0,
        "无结果次数": 0,
        "总注入次数": 0,
        "平均检索分数": 0,
        "最高检索分数": 0,
        "最常查询": [],
        "检索时间分布": defaultdict(int)
    }
    
    queries = []
    all_scores = []
    
    for log in logs:
        log_type = log.get("type", "")
        
        if log_type == "retrieval_start":
            stats["总检索次数"] += 1
            queries.append(log.get("query", ""))
            
            # 按小时统计
            timestamp = log.get("timestamp", "")
            if timestamp:
                try:
                    dt = datetime.datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                    hour = dt.hour
                    stats["检索时间分布"][hour] += 1
                except:
                    pass
        
        elif log_type == "retrieval_result":
            result_count = log.get("result_count", 0)
            if result_count > 0:
                stats["成功检索次数"] += 1
                # 提取分数
                nodes = log.get("nodes", [])
                for node in nodes:
                    score = node.get("score", 0)
                    all_scores.append(score)
                    if score > stats["最高检索分数"]:
                        stats["最高检索分数"] = score
            else:
                stats["无结果次数"] += 1
        
        elif log_type == "context_injection":
            stats["总注入次数"] += 1
    
    # 计算平均分数
    if all_scores:
        stats["平均检索分数"] = sum(all_scores) / len(all_scores)
    
    # 最常查询（前5）
    query_counter = Counter(queries)
    stats["最常查询"] = query_counter.most_common(5)
    
    return stats


def analyze_query_details(logs: List[Dict], limit: int = 10) -> List[Dict]:
    """分析查询详情"""
    query_details = []
    
    # 按查询分组
    query_groups = defaultdict(list)
    for log in logs:
        if log.get("type") == "retrieval_start":
            query = log.get("query", "")
            query_groups[query].append(log)
    
    # 分析每个查询
    for query, start_logs in query_groups.items():
        detail = {
            "查询": query,
            "检索次数": len(start_logs),
            "首次时间": start_logs[0].get("timestamp", ""),
            "检索结果": [],
            "注入情况": []
        }
        
        # 查找对应的检索结果
        for log in logs:
            if (log.get("type") == "retrieval_result" and 
                log.get("query") == query):
                nodes = log.get("nodes", [])
                if nodes:
                    detail["检索结果"] = nodes[:3]  # 只保留前3个结果
                    break
        
        # 查找注入情况
        for log in logs:
            if log.get("type") == "context_injection":
                detail["注入情况"].append({
                    "注入数量": log.get("injected_count", 0),
                    "上下文长度": log.get("context_length", 0),
                    "平均分数": log.get("average_score", 0)
                })
        
        query_details.append(detail)
    
    # 按检索次数排序
    query_details.sort(key=lambda x: x["检索次数"], reverse=True)
    
    return query_details[:limit]


def print_summary_report(stats: Dict[str, Any]):
    """打印汇总报告"""
    print("\n" + "="*60)
    print("🔍 隐藏知识库每日统计报告")
    print("="*60)
    
    print(f"\n📊 基础统计:")
    print(f"  • 总检索次数: {stats['总检索次数']}")
    print(f"  • 成功检索次数: {stats['成功检索次数']}")
    print(f"  • 无结果次数: {stats['无结果次数']}")
    print(f"  • 总注入次数: {stats['总注入次数']}")
    
    if stats['总检索次数'] > 0:
        success_rate = (stats['成功检索次数'] / stats['总检索次数']) * 100
        print(f"  • 检索成功率: {success_rate:.1f}%")
    
    print(f"\n📈 分数统计:")
    print(f"  • 平均检索分数: {stats['平均检索分数']:.4f}")
    print(f"  • 最高检索分数: {stats['最高检索分数']:.4f}")
    
    print(f"\n🔥 热门查询 (前5):")
    for i, (query, count) in enumerate(stats['最常查询'], 1):
        print(f"  {i}. {query[:50]}... ({count}次)")
    
    print(f"\n⏰ 检索时间分布:")
    for hour in sorted(stats['检索时间分布'].keys()):
        count = stats['检索时间分布'][hour]
        print(f"  • {hour:02d}:00-{hour:02d}:59: {count}次")


def print_query_details(query_details: List[Dict]):
    """打印查询详情"""
    print("\n" + "="*60)
    print("🔍 查询详情报告 (前10)")
    print("="*60)
    
    for i, detail in enumerate(query_details, 1):
        print(f"\n{i}. 查询: {detail['查询']}")
        print(f"   检索次数: {detail['检索次数']}")
        print(f"   首次时间: {detail['首次时间']}")
        
        if detail['检索结果']:
            print(f"   检索结果:")
            for j, node in enumerate(detail['检索结果'], 1):
                score = node.get('score', 0)
                preview = node.get('content_preview', '')[:50]
                print(f"     {j}. 分数: {score:.4f} | 内容: {preview}...")
        else:
            print(f"   检索结果: 无")
        
        if detail['注入情况']:
            injection = detail['注入情况'][0]  # 取第一次注入
            print(f"   注入情况: {injection['注入数量']}条 | "
                  f"上下文: {injection['上下文长度']}字符 | "
                  f"平均分: {injection['平均分数']:.4f}")


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="分析隐藏知识库日志")
    parser.add_argument("--date", type=str, help="指定日期 (YYYY-MM-DD)，默认今天")
    parser.add_argument("--detail", action="store_true", help="显示详细查询信息")
    parser.add_argument("--json", action="store_true", help="输出 JSON 格式")
    
    args = parser.parse_args()
    
    # 加载日志
    logs = load_json_logs(args.date)
    if not logs:
        return
    
    # 分析统计
    stats = analyze_daily_stats(logs)
    
    if args.json:
        print(json.dumps(stats, ensure_ascii=False, indent=2))
    else:
        print_summary_report(stats)
        
        if args.detail:
            query_details = analyze_query_details(logs)
            print_query_details(query_details)


if __name__ == "__main__":
    main()
