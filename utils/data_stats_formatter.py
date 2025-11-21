# -*- coding: utf-8 -*-
"""
数据统计格式化工具
将统计数据转换为可读的文本格式，用于 LLM 分析
"""
from typing import Dict, Any, List, Tuple


def format_number(num: int) -> str:
    """格式化数字，添加千分位分隔符"""
    return f"{num:,}"


def calculate_percentage(part: int, total: int) -> str:
    """计算百分比，确保清晰度"""
    if total > 0:
        return f"{part / total * 100:.1f}%"
    return "0.0%"


def format_top_n_stats(stats_dict: Dict[str, int], top_n: int = 3, total: int = None) -> str:
    """
    格式化统计字典，只显示前N项，其余归为"其他"
    
    Args:
        stats_dict: 统计字典 {key: count}
        top_n: 显示前N项
        total: 总数（用于计算百分比），如果为None则使用stats_dict的总和
        
    Returns:
        格式化后的文本
    """
    if not stats_dict:
        return "该项数据未提供"
    
    # 计算总数
    if total is None:
        total = sum(stats_dict.values())
    
    if total == 0:
        return "无数据"
    
    # 按数量降序排序
    sorted_items = sorted(stats_dict.items(), key=lambda x: x[1], reverse=True)
    
    # 构建结果
    result_parts = []
    
    # 前N项
    top_items = sorted_items[:top_n]
    for key, count in top_items:
        percentage = calculate_percentage(count, total)
        result_parts.append(f"{key} {format_number(count)}人({percentage})")
    
    # 其他项
    if len(sorted_items) > top_n:
        other_count = sum(count for _, count in sorted_items[top_n:])
        other_percentage = calculate_percentage(other_count, total)
        result_parts.append(f"其他 {format_number(other_count)}人({other_percentage})")
    
    return "、".join(result_parts)


def format_data_stats(data: Dict[str, Any]) -> str:
    """
    将统计数据格式化为可读文本
    
    Args:
        data: 统计数据字典
        
    Returns:
        格式化后的文本块
    """
    lines = []
    lines.append("=" * 50)
    lines.append("出入境人员统计数据")
    lines.append("=" * 50)
    lines.append("")
    
    # 1. 总体统计
    total_count = data.get("totalCount", 0)
    entry_count = data.get("entryCount", 0)
    exit_count = data.get("exitCount", 0)
    
    lines.append("【总体统计】")
    lines.append(f"总人数: {format_number(total_count)}人")
    
    if total_count > 0:
        lines.append(f"入境人数: {format_number(entry_count)}人 ({calculate_percentage(entry_count, total_count)})")
        lines.append(f"出境人数: {format_number(exit_count)}人 ({calculate_percentage(exit_count, total_count)})")
    else:
        lines.append("入境人数: 该项数据未提供")
        lines.append("出境人数: 该项数据未提供")
    
    lines.append("")
    
    # 2. 性别分布
    male_count = data.get("maleCount", 0)
    female_count = data.get("femaleCount", 0)
    
    lines.append("【性别分布】")
    if total_count > 0:
        lines.append(f"男性: {format_number(male_count)}人 ({calculate_percentage(male_count, total_count)})")
        lines.append(f"女性: {format_number(female_count)}人 ({calculate_percentage(female_count, total_count)})")
    else:
        lines.append("该项数据未提供")
    
    lines.append("")
    
    # 3. 交通工具统计
    transportation_tool_stats = data.get("transportationToolStats", {})
    lines.append("【交通工具统计】")
    if transportation_tool_stats:
        lines.append(format_top_n_stats(transportation_tool_stats, top_n=5, total=total_count))
    else:
        lines.append("该项数据未提供")
    
    lines.append("")
    
    # 4. 国家/地区统计
    country_region_stats = data.get("countryRegionStats", {})
    lines.append("【国家/地区统计】")
    if country_region_stats:
        lines.append(format_top_n_stats(country_region_stats, top_n=5, total=total_count))
    else:
        lines.append("该项数据未提供")
    
    lines.append("")
    
    # 5. 交通方式统计
    transportation_mode_stats = data.get("transportationModeStats", {})
    lines.append("【交通方式统计】")
    if transportation_mode_stats:
        # 交通方式代码映射
        mode_mapping = {
            "1": "航空",
            "2": "陆路",
            "3": "水路",
            "4": "铁路"
        }
        # 转换代码为名称
        mode_stats_with_names = {
            mode_mapping.get(k, f"方式{k}"): v 
            for k, v in transportation_mode_stats.items()
        }
        lines.append(format_top_n_stats(mode_stats_with_names, top_n=5, total=total_count))
    else:
        lines.append("该项数据未提供")
    
    lines.append("")
    
    # 6. 人员类别统计
    person_category_stats = data.get("personCategoryStats", {})
    lines.append("【人员类别统计】")
    if person_category_stats:
        # 人员类别代码映射（根据实际业务调整）
        category_mapping = {
            "26": "普通旅客",
            "01": "外交人员",
            "02": "公务人员",
            "03": "商务人员",
            "04": "劳务人员",
            "05": "留学人员"
        }
        category_stats_with_names = {
            category_mapping.get(k, f"类别{k}"): v 
            for k, v in person_category_stats.items()
        }
        lines.append(format_top_n_stats(category_stats_with_names, top_n=5, total=total_count))
    else:
        lines.append("该项数据未提供")
    
    lines.append("")
    
    # 7. 民族统计
    ethnicity_stats = data.get("ethnicityStats", {})
    lines.append("【民族统计】")
    if ethnicity_stats:
        lines.append(format_top_n_stats(ethnicity_stats, top_n=5, total=total_count))
    else:
        lines.append("该项数据未提供")
    
    lines.append("")
    lines.append("=" * 50)
    lines.append("注：缺失的统计项已标注为'未提供'")
    lines.append("=" * 50)
    
    return "\n".join(lines)


def validate_data_stats(data: Dict[str, Any]) -> Tuple[bool, str]:
    """
    验证统计数据的有效性
    
    Args:
        data: 统计数据字典
        
    Returns:
        (是否有效, 错误信息)
    """
    if not isinstance(data, dict):
        return False, "数据格式错误：必须是字典类型"
    
    # 检查是否至少有总人数
    if "totalCount" not in data:
        return False, "缺少必需字段：totalCount"
    
    total_count = data.get("totalCount", 0)
    if not isinstance(total_count, (int, float)) or total_count < 0:
        return False, "totalCount 必须是非负数字"
    
    # 检查基础数值字段
    numeric_fields = ["entryCount", "exitCount", "maleCount", "femaleCount"]
    for field in numeric_fields:
        value = data.get(field, 0)
        if not isinstance(value, (int, float)) or value < 0:
            return False, f"{field} 必须是非负数字"
    
    # 检查出入境人数的合理性
    entry_count = data.get("entryCount", 0)
    exit_count = data.get("exitCount", 0)
    
    if entry_count + exit_count > total_count * 1.1:  # 允许10%的误差
        return False, f"出入境人数之和({entry_count + exit_count})超过总人数({total_count})"
    
    # 检查性别人数的合理性
    male_count = data.get("maleCount", 0)
    female_count = data.get("femaleCount", 0)
    
    if male_count + female_count > total_count * 1.1:  # 允许10%的误差
        return False, f"男女人数之和({male_count + female_count})超过总人数({total_count})"
    
    # 检查统计字典中的值
    dict_fields = [
        "transportationToolStats", 
        "countryRegionStats", 
        "transportationModeStats", 
        "personCategoryStats", 
        "ethnicityStats"
    ]
    
    for field in dict_fields:
        stats_dict = data.get(field, {})
        if not isinstance(stats_dict, dict):
            return False, f"{field} 必须是字典类型"
        
        # 检查每个值都是非负数字
        for key, value in stats_dict.items():
            if not isinstance(key, str) or not key.strip():
                return False, f"{field} 中的键必须是非空字符串"
            
            if not isinstance(value, (int, float)) or value < 0:
                return False, f"{field} 中 '{key}' 的值必须是非负数字，当前值: {value}"
    
    return True, ""
