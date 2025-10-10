# -*- coding: utf-8 -*-
"""
知识库服务层
负责知识库索引的构建、加载和管理
"""
import os
import json
import shutil
from typing import Tuple, Optional, List
from llama_index.core import (
    SimpleDirectoryReader,
    StorageContext,
    VectorStoreIndex,
    load_index_from_storage,
    ServiceContext,
    Settings
)
from llama_index.core.schema import TextNode
from config import Settings as AppSettings
from core import DocumentProcessor, RetrieverFactory
from utils.logger import logger


class KnowledgeService:
    """知识库服务管理器"""

    def __init__(self, llm):
        self.llm = llm
        self.index = None
        self.all_nodes = None
        self.retriever = None
        self.doc_processor = DocumentProcessor(AppSettings.CHUNK_CHAR_B)

    def build_or_load_index(self) -> Tuple[Optional[VectorStoreIndex], Optional[List[TextNode]]]:
        """
        构建或加载知识库索引

        Returns:
            (索引, 所有节点) 元组
        """
        storage_path = AppSettings.STORAGE_PATH
        kb_dir = AppSettings.KNOWLEDGE_BASE_DIR
        hashes_file = os.path.join(storage_path, "kb_hashes.json")

        # 确保知识库目录存在
        os.makedirs(kb_dir, exist_ok=True)

        if not any(os.scandir(kb_dir)):
            logger.warning("知识库文件夹为空，无法构建索引")
            return None, None

        # 检查是否需要重建索引
        if self._should_rebuild_index(storage_path, hashes_file, kb_dir):
            return self._build_index(storage_path, kb_dir, hashes_file)
        else:
            return self._load_index(storage_path)

    def create_retriever(self):
        """创建混合检索器"""
        if self.index is None or self.all_nodes is None:
            logger.error("索引或节点未初始化，无法创建检索器")
            return None

        self.retriever = RetrieverFactory.create_hybrid_retriever(
            self.index,
            self.all_nodes,
            AppSettings.RETRIEVAL_TOP_K
        )
        return self.retriever

    def _should_rebuild_index(
        self,
        storage_path: str,
        hashes_file: str,
        kb_dir: str
    ) -> bool:
        """判断是否需要重建索引"""
        if not os.path.exists(storage_path) or not os.path.exists(hashes_file):
            return True

        logger.info("检查知识库文件变化...")
        current_hashes = DocumentProcessor.compute_file_hashes(kb_dir)
        current_hashes_str = json.dumps(current_hashes, sort_keys=True)

        try:
            with open(hashes_file, "r", encoding="utf-8") as f:
                saved_hashes_str = f.read()

            if saved_hashes_str == current_hashes_str:
                logger.info("知识库未变化，将加载现有索引")
                return False
        except Exception as e:
            logger.warning(f"无法读取哈希文件: {e}")

        return True

    def _load_index(
        self,
        storage_path: str
    ) -> Tuple[Optional[VectorStoreIndex], Optional[List[TextNode]]]:
        """加载已有索引"""
        try:
            logger.info("从本地加载索引...")

            # 确保全局 Embedding 已设置
            if Settings.embed_model is None:
                raise ValueError("全局 Embed model 未设置")

            service_context = ServiceContext.from_defaults(
                llm=self.llm,
                embed_model=Settings.embed_model
            )

            storage_context = StorageContext.from_defaults(persist_dir=storage_path)
            index = load_index_from_storage(storage_context, service_context=service_context)

            all_nodes = list(storage_context.docstore.docs.values())
            if not all_nodes:
                raise ValueError("未找到任何节点")

            logger.info(f"成功加载索引，共 {len(all_nodes)} 个节点")
            self.index = index
            self.all_nodes = all_nodes
            return index, all_nodes

        except Exception as e:
            logger.error(f"加载索引失败: {e}，将重新构建", exc_info=True)
            return None, None

    def _build_index(
        self,
        storage_path: str,
        kb_dir: str,
        hashes_file: str
    ) -> Tuple[Optional[VectorStoreIndex], Optional[List[TextNode]]]:
        """构建新索引"""
        logger.info("开始构建新索引...")

        # 清理旧索引
        if os.path.exists(storage_path):
            shutil.rmtree(storage_path)
        os.makedirs(storage_path)

        # 读取文档
        file_metadata_fn = lambda x: {
            "file_name": os.path.basename(x),
            "file_path": x
        }

        docs = SimpleDirectoryReader(
            kb_dir,
            recursive=True,
            file_metadata=file_metadata_fn,
            exclude=["*.doc", "*.tmp"]
        ).load_data(show_progress=True)

        if not docs:
            logger.warning("未找到可加载的文档")
            return None, None

        # 切分文档
        all_nodes = self.doc_processor.split_documents(docs)
        if not all_nodes:
            logger.warning("文档切分后未产生有效节点")
            return None, None

        # 构建索引
        logger.info("生成 Embeddings...")
        storage_context = StorageContext.from_defaults()
        storage_context.docstore.add_documents(all_nodes)

        service_context = ServiceContext.from_defaults(
            llm=self.llm,
            embed_model=Settings.embed_model
        )

        index = VectorStoreIndex(
            all_nodes,
            storage_context=storage_context,
            service_context=service_context,
            show_progress=True
        )

        # 持久化
        logger.info("持久化索引...")
        index.storage_context.persist(persist_dir=storage_path)

        # 保存哈希
        current_hashes = DocumentProcessor.compute_file_hashes(kb_dir)
        with open(hashes_file, "w", encoding="utf-8") as f:
            json.dump(current_hashes, f, sort_keys=True)

        logger.info(f"索引构建完成，共 {len(all_nodes)} 个节点")
        self.index = index
        self.all_nodes = all_nodes
        return index, all_nodes

