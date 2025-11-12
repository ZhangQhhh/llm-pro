# -*- coding: utf-8 -*-
"""
节点过滤器
用于对检索到的节点进行智能过滤和提取
"""
import json
import time
from typing import List, Dict, Any, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
from utils import logger
from prompts import get_insertblock_system_all, get_insertblock_user_all
from config import Settings


class InsertBlockFilter:
    """
    基于 insertBlock 提示词的节点过滤器
    对每个节点判断是否能回答问题，并提取关键段落
    """

    def __init__(self, llm_service, max_workers: int = None):
        """
        Args:
            llm_service: LLM 服务实例
            max_workers: 并发处理的最大线程数（None 则使用配置值）
        """
        self.llm_service = llm_service
        self.max_workers = max_workers or Settings.INSERTBLOCK_MAX_WORKERS
        logger.info(f"InsertBlockFilter 初始化 | 并发数: {self.max_workers}")

    def filter_nodes(
        self,
        question: str,
        nodes: List[Any],
        llm_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        并发处理多个节点，判断每个节点是否能回答问题

        Args:
            question: 用户问题
            nodes: 重排后的节点列表
            llm_id: 使用的 LLM ID，默认使用 default

        Returns:
            过滤后的节点列表，每个包含：
            {
                "node": 原始节点,
                "file_name": 文件名,
                "is_relevant": 是否相关,
                "can_answer": 是否能回答,
                "reasoning": 推理过程,
                "answer": 答案,
                "key_passage": 关键段落,
                "initial_score": 初始分数,
                "reranked_score": 重排分数
            }
        """
        if not nodes:
            return []

        start_time = time.time()
        logger.info(f"开始使用 InsertBlock 过滤器处理 {len(nodes)} 个节点 | 并发数: {self.max_workers}")

        # 获取 LLM 实例
        llm = self.llm_service.get_client(llm_id)
        if not llm:
            logger.error("无法获取 LLM 实例，返回空结果")
            return []

        filtered_results = []
        rejected_nodes = []  # 记录被拒绝的节点
        file_stats = {}  # 统计每个文件的节点数

        # 使用线程池并发处理
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # 提交所有任务
            future_to_node = {
                executor.submit(
                    self._process_single_node,
                    question,
                    node,
                    llm
                ): node
                for node in nodes
            }

            # 收集结果
            for future in as_completed(future_to_node):
                node = future_to_node[future]
                try:
                    result = future.result()
                    if result:
                        file_name = result['file_name']
                        # 统计文件
                        file_stats[file_name] = file_stats.get(file_name, 0) + 1

                        if result.get("can_answer"):
                            filtered_results.append(result)
                            logger.info(
                                f"✓ 节点通过 [{file_stats[file_name]}] {file_name} | "
                                f"关键段落: {len(result.get('key_passage', ''))} 字符 | "
                                f"推理: {result['reasoning'][:50]}..."
                            )
                        else:
                            rejected_nodes.append(result)
                            logger.info(
                                f"✗ 节点拒绝 [{file_stats[file_name]}] {file_name} | "
                                f"推理: {result['reasoning'][:50]}..."
                            )
                    else:
                        file_name = node.node.metadata.get('file_name', '未知')
                        logger.debug(f"节点处理返回 None: {file_name}")
                except Exception as e:
                    logger.error(
                        f"处理节点失败: {node.node.metadata.get('file_name', '未知')} | "
                        f"错误: {e}"
                    )

        # 计算处理时间
        elapsed_time = time.time() - start_time
        avg_time_per_node = elapsed_time / len(nodes) if nodes else 0
        
        # 输出详细统计
        logger.info("=" * 60)
        logger.info(f"InsertBlock 过滤完成统计:")
        logger.info(f"  总节点数: {len(nodes)}")
        logger.info(f"  通过筛选: {len(filtered_results)} 个节点")
        logger.info(f"  被拒绝: {len(rejected_nodes)} 个节点")
        logger.info(f"  处理失败: {len(nodes) - len(filtered_results) - len(rejected_nodes)} 个节点")
        logger.info(f"  总处理时间: {elapsed_time:.2f} 秒")
        logger.info(f"  平均每节点: {avg_time_per_node:.2f} 秒")
        logger.info(f"  并发数: {self.max_workers}")
        logger.info(f"\n  涉及文件数: {len(file_stats)}")

        # 按文件输出统计
        for file_name, count in sorted(file_stats.items()):
            passed = sum(1 for r in filtered_results if r['file_name'] == file_name)
            rejected = sum(1 for r in rejected_nodes if r['file_name'] == file_name)
            logger.info(f"    - {file_name}: {count} 个节点 (通过:{passed}, 拒绝:{rejected})")

        logger.info("=" * 60)

        return filtered_results

    def _process_single_node(
        self,
        question: str,
        node: Any,
        llm: Any
    ) -> Optional[Dict[str, Any]]:
        """
        处理单个节点

        Args:
            question: 用户问题
            node: 节点对象
            llm: LLM 实例

        Returns:
            处理结果字典或 None
        """
        # 初始化变量（用于异常处理）
        file_name = "未知文件"
        response_text = ""

        try:
            # 提取节点信息
            file_name = node.node.metadata.get('file_name', '未知文件')
            regulations = node.node.get_content().strip()
            initial_score = node.node.metadata.get('initial_score', 0.0)
            reranked_score = node.score

            # 构造提示词
            system_template = get_insertblock_system_all()
            user_template = get_insertblock_user_all()

            # 拼接提示词（system 和 user 都是列表）
            # 先对模板进行 format，再 join
            # 注意：只对包含占位符的模板进行 format
            system_prompt_parts = []
            for template in system_template:
                # 检查是否包含占位符
                if "{question}" in template or "{regulations}" in template:
                    system_prompt_parts.append(template.format(question=question, regulations=regulations))
                else:
                    system_prompt_parts.append(template)
            system_prompt = "\n".join(system_prompt_parts)

            # user_template 通常不包含需要 format 的占位符
            user_prompt_parts = []
            for template in user_template:
                if "{question}" in template or "{regulations}" in template:
                    user_prompt_parts.append(template.format(question=question, regulations=regulations))
                else:
                    user_prompt_parts.append(template)
            user_prompt = "\n".join(user_prompt_parts)

            # 组合为单一 prompt
            full_prompt = f"{system_prompt}\n\n{user_prompt}"

            # 调用 LLM
            response = llm.complete(full_prompt)
            response_text = response.text.strip()

            # 解析 JSON 响应
            # 尝试提取 JSON（可能包含在 markdown 代码块中）
            json_text = self._extract_json(response_text)
            result_data = json.loads(json_text)

            # 构造返回结果
            return {
                "node": node,
                "file_name": file_name,
                "is_relevant": result_data.get("is_relevant", False),
                "can_answer": result_data.get("can_answer", False),
                "reasoning": result_data.get("reasoning", ""),
                "answer": result_data.get("answer", ""),
                "key_passage": result_data.get("key_passage"),
                "initial_score": initial_score,
                "reranked_score": reranked_score
            }

        except json.JSONDecodeError as e:
            logger.error(
                f"JSON 解析失败: {file_name} | 响应: {response_text[:200]} | 错误: {e}"
            )
            return None
        except Exception as e:
            logger.error(f"处理节点异常: {file_name} | 错误: {e}")
            return None

    @staticmethod
    def _extract_json(text: str) -> str:
        """
        从文本中提取 JSON
        支持提取 markdown 代码块中的 JSON

        Args:
            text: 可能包含 JSON 的文本

        Returns:
            提取的 JSON 字符串
        """
        # 去除首尾空白
        text = text.strip()

        # 尝试提取 markdown 代码块
        if "```json" in text:
            start = text.find("```json") + 7
            end = text.find("```", start)
            if end != -1:
                return text[start:end].strip()
        elif "```" in text:
            start = text.find("```") + 3
            end = text.find("```", start)
            if end != -1:
                return text[start:end].strip()

        # 尝试查找 JSON 对象
        start = text.find("{")
        end = text.rfind("}") + 1
        if start != -1 and end > start:
            return text[start:end]

        return text
