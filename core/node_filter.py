# -*- coding: utf-8 -*-
"""
节点过滤器
用于对检索到的节点进行智能过滤和提取
"""
import json
from typing import List, Dict, Any, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
from utils import get_prompt, logger


class InsertBlockFilter:
    """
    基于 insertBlock 提示词的节点过滤器
    对每个节点判断是否能回答问题，并提取关键段落
    """

    def __init__(self, llm_service, max_workers: int = 5):
        """
        Args:
            llm_service: LLM 服务实例
            max_workers: 并发处理的最大线程数
        """
        self.llm_service = llm_service
        self.max_workers = max_workers

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

        logger.info(f"开始使用 InsertBlock 过滤器处理 {len(nodes)} 个节点")

        # 获取 LLM 实例
        llm = self.llm_service.get_llm(llm_id)
        if not llm:
            logger.error("无法获取 LLM 实例，返回空结果")
            return []

        filtered_results = []

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
                    if result and result.get("can_answer"):
                        filtered_results.append(result)
                        logger.info(
                            f"节点可回答: {result['file_name']} | "
                            f"关键段落长度: {len(result.get('key_passage', ''))}"
                        )
                    else:
                        logger.debug(
                            f"节点不可回答: {node.node.metadata.get('file_name', '未知')}"
                        )
                except Exception as e:
                    logger.error(
                        f"处理节点失败: {node.node.metadata.get('file_name', '未知')} | "
                        f"错误: {e}"
                    )

        logger.info(
            f"InsertBlock 过滤完成: {len(nodes)} 个节点 -> {len(filtered_results)} 个可回答节点"
        )

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
            system_template = get_prompt(
                "insertBlock.system.all",
                ["# 角色\n你是一位精通中国出入境边防检查各项业务的专家。"]
            )
            user_template = get_prompt(
                "insertBlock.user.all",
                ["# 任务\n请分析法规是否能回答问题。"]
            )

            # 拼接提示词（system 和 user 都是列表）
            system_prompt = "\n".join(system_template).format(
                question=question,
                regulations=regulations
            )
            user_prompt = "\n".join(user_template)

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
