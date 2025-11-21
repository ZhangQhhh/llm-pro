# -*- coding: utf-8 -*-
"""
快速检索分数诊断脚本
简化版本，避免复杂的依赖问题
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import Settings as AppSettings
from utils.logger import logger


def check_config():
    """检查配置参数"""
    
    logger.info("=" * 80)
    logger.info("检索配置检查工具")
    logger.info("=" * 80)
    
    logger.info("\n[RRF融合配置]")
    logger.info(f"  RRF_K: {AppSettings.RRF_K}")
    logger.info(f"  RRF_VECTOR_WEIGHT: {AppSettings.RRF_VECTOR_WEIGHT}")
    logger.info(f"  RRF_BM25_WEIGHT: {AppSettings.RRF_BM25_WEIGHT}")
    
    # 计算理论分数
    logger.info("\n[理论分数计算（RRF融合后）]")
    for rank in [1, 2, 3, 5, 10, 20]:
        vector_score = AppSettings.RRF_VECTOR_WEIGHT * (1.0 / (AppSettings.RRF_K + rank))
        bm25_score = AppSettings.RRF_BM25_WEIGHT * (1.0 / (AppSettings.RRF_K + rank))
        total_score = vector_score + bm25_score
        logger.info(f"  第{rank:2d}名: 向量={vector_score:.4f} + BM25={bm25_score:.4f} = 总分={total_score:.4f}")
    
    logger.info("\n[检索参数]")
    logger.info(f"  RETRIEVAL_TOP_K: {AppSettings.RETRIEVAL_TOP_K}")
    logger.info(f"  RETRIEVAL_TOP_K_BM25: {AppSettings.RETRIEVAL_TOP_K_BM25}")
    logger.info(f"  RERANK_TOP_N: {AppSettings.RERANK_TOP_N}")
    logger.info(f"  RERANKER_INPUT_TOP_N: {AppSettings.RERANKER_INPUT_TOP_N}")
    logger.info(f"  RERANK_SCORE_THRESHOLD: {AppSettings.RERANK_SCORE_THRESHOLD}")
    
    logger.info("\n[模型配置]")
    logger.info(f"  EMBED_MODEL_PATH: {AppSettings.EMBED_MODEL_PATH}")
    logger.info(f"  RERANKER_MODEL_PATH: {AppSettings.RERANKER_MODEL_PATH}")
    logger.info(f"  DEVICE: {AppSettings.DEVICE}")
    
    logger.info("\n[知识库路径]")
    logger.info(f"  KNOWLEDGE_BASE_DIR: {AppSettings.KNOWLEDGE_BASE_DIR}")
    logger.info(f"  STORAGE_PATH: {AppSettings.STORAGE_PATH}")
    logger.info(f"  QDRANT_HOST: {AppSettings.QDRANT_HOST}")
    logger.info(f"  QDRANT_PORT: {AppSettings.QDRANT_PORT}")
    logger.info(f"  QDRANT_COLLECTION: {AppSettings.QDRANT_COLLECTION}")
    
    logger.info("\n[分数优化建议]")
    if AppSettings.RRF_K <= 5.0:
        logger.info("  ✓ RRF_K 已优化（≤5.0），分数范围合理")
    else:
        logger.warning(f"  ⚠️ RRF_K 过大（{AppSettings.RRF_K}），建议降低到5.0以下")
    
    if AppSettings.RRF_VECTOR_WEIGHT >= 0.6:
        logger.info("  ✓ 向量权重合理（≥0.6）")
    else:
        logger.warning(f"  ⚠️ 向量权重过低（{AppSettings.RRF_VECTOR_WEIGHT}），建议提高到0.6-0.8")
    
    if AppSettings.RERANK_SCORE_THRESHOLD <= 0.3:
        logger.info("  ✓ 重排序阈值合理（≤0.3）")
    else:
        logger.warning(f"  ⚠️ 重排序阈值过高（{AppSettings.RERANK_SCORE_THRESHOLD}），可能过滤掉相关结果")
    
    logger.info("\n[修复效果预期]")
    old_k = 10.0  # 修复前的值
    new_k = AppSettings.RRF_K
    old_score = 1.0 / (old_k + 1)
    new_score = 1.0 / (new_k + 1)
    improvement = (new_score - old_score) / old_score * 100
    logger.info(f"  第1名分数提升: {old_score:.4f} → {new_score:.4f} (+{improvement:.1f}%)")
    logger.info(f"  第5名分数提升: {1.0/(old_k+5):.4f} → {1.0/(new_k+5):.4f}")
    
    logger.info("\n" + "=" * 80)
    logger.info("配置检查完成！")
    logger.info("=" * 80)


if __name__ == "__main__":
    try:
        check_config()
    except Exception as e:
        import logging
        logging.error(f"检查失败: {e}", exc_info=True)
