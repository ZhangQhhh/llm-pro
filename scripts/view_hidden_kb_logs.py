#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
快速查看隐藏知识库日志
"""
import os
import datetime
import argparse


def view_today_logs():
    """查看今天的日志"""
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    log_file = f"logs/hidden_logs/hidden_kb_{today}.log"
    
    if not os.path.exists(log_file):
        print(f"❌ 今天的日志文件不存在: {log_file}")
        print("💡 可能还没有隐藏知识库的检索记录")
        return
    
    print(f"📄 查看隐藏知识库日志: {log_file}")
    print("="*80)
    
    try:
        with open(log_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            
        if not lines:
            print("📝 日志文件为空")
            return
        
        print(f"📊 总记录数: {len(lines)}")
        print("\n📋 最近10条记录:")
        print("-"*80)
        
        # 显示最后10条记录
        for line in lines[-10:]:
            print(line.strip())
            
    except Exception as e:
        print(f"❌ 读取日志失败: {e}")


def search_logs(keyword: str, date: str = None):
    """搜索包含关键词的日志"""
    if date is None:
        date = datetime.datetime.now().strftime("%Y-%m-%d")
    
    log_file = f"logs/hidden_logs/hidden_kb_{date}.log"
    
    if not os.path.exists(log_file):
        print(f"❌ 日志文件不存在: {log_file}")
        return
    
    print(f"🔍 搜索日志: {log_file}")
    print(f"🔑 关键词: {keyword}")
    print("="*80)
    
    try:
        with open(log_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        matched_lines = []
        for i, line in enumerate(lines, 1):
            if keyword.lower() in line.lower():
                matched_lines.append((i, line.strip()))
        
        if not matched_lines:
            print(f"📝 未找到包含 '{keyword}' 的记录")
            return
        
        print(f"📊 找到 {len(matched_lines)} 条匹配记录:")
        print("-"*80)
        
        for line_num, line in matched_lines:
            print(f"[{line_num:3d}] {line}")
            
    except Exception as e:
        print(f"❌ 搜索失败: {e}")


def list_log_files():
    """列出所有日志文件"""
    log_dir = "logs/hidden_logs"
    
    if not os.path.exists(log_dir):
        print(f"❌ 日志目录不存在: {log_dir}")
        return
    
    try:
        files = os.listdir(log_dir)
        log_files = [f for f in files if f.endswith('.log') or f.endswith('.json')]
        
        if not log_files:
            print("📝 没有找到日志文件")
            return
        
        print("📂 隐藏知识库日志文件列表:")
        print("-"*60)
        
        for file in sorted(log_files):
            file_path = os.path.join(log_dir, file)
            size = os.path.getsize(file_path)
            mtime = datetime.datetime.fromtimestamp(os.path.getmtime(file_path))
            print(f"  📄 {file} | {size:,} bytes | {mtime.strftime('%Y-%m-%d %H:%M:%S')}")
            
    except Exception as e:
        print(f"❌ 列出文件失败: {e}")


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="查看隐藏知识库日志")
    parser.add_argument("--today", action="store_true", help="查看今天的日志")
    parser.add_argument("--search", type=str, help="搜索包含关键词的日志")
    parser.add_argument("--date", type=str, help="指定日期 (YYYY-MM-DD)")
    parser.add_argument("--list", action="store_true", help="列出所有日志文件")
    
    args = parser.parse_args()
    
    if args.list:
        list_log_files()
    elif args.search:
        search_logs(args.search, args.date)
    elif args.today:
        view_today_logs()
    else:
        # 默认查看今天的日志
        view_today_logs()
        
        print("\n" + "="*80)
        print("💡 使用提示:")
        print("  python scripts/view_hidden_kb_logs.py --today     # 查看今天日志")
        print("  python scripts/view_hidden_kb_logs.py --search 关键词  # 搜索日志")
        print("  python scripts/view_hidden_kb_logs.py --list      # 列出所有日志文件")
        print("  python scripts/analyze_hidden_kb_logs.py --detail # 详细分析报告")


if __name__ == "__main__":
    main()
