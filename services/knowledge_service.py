# -*- coding: utf-8 -*-
"""
知识库服务层
负责知识库索引的构建、加载和管理
"""
import os
import json
import shutil
from qdrant_client import QdrantClient
from llama_index.vector_stores.qdrant import QdrantVectorStore
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
        # 通用知识库
        self.index = None
        self.all_nodes = None
        self.retriever = None
        # 免签政策知识库
        self.visa_free_index = None
        self.visa_free_nodes = None
        self.visa_free_retriever = None
        
        self.doc_processor = DocumentProcessor(AppSettings.CHUNK_CHAR_B)
        # 初始化 Qdrant 客户端(Docker 模式)
        self.qdrant_client = QdrantClient(
            host=AppSettings.QDRANT_HOST,
            port=AppSettings.QDRANT_PORT
        )

        # 对话管理器初始化为 None(需要在 embed_model 设置后初始化)
        self.conversation_manager = None

        # 内嵌模式(无需 Docker,取消注释使用)
        # self.qdrant_client = QdrantClient(
        #     path=AppSettings.QDRANT_PATH
        # )
        logger.info("Qdrant 客户端初始化成功")

    def initialize_conversation_manager(self):
        """初始化对话管理器(需在 embed_model 设置后调用)"""
        if Settings.embed_model is None:
            raise ValueError("Embed model 未设置,无法初始化对话管理器")

        from services.conversation_manager import ConversationManager
        self.conversation_manager = ConversationManager(
            embed_model=Settings.embed_model,
            qdrant_client=self.qdrant_client
        )
        logger.info("对话管理器初始化成功")

    def build_or_load_index(self) -> Tuple[Optional[VectorStoreIndex], Optional[List[TextNode]]]:
        """
        构建或加载通用知识库索引

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
        if self._should_rebuild_index(storage_path, hashes_file, kb_dir, AppSettings.QDRANT_COLLECTION):
            return self._build_index(storage_path, kb_dir, hashes_file, AppSettings.QDRANT_COLLECTION)
        else:
            # return self._load_index(storage_path)  先暂时一直重建
            return self._build_index(storage_path, kb_dir, hashes_file, AppSettings.QDRANT_COLLECTION)

    def build_or_load_visa_free_index(self) -> Tuple[Optional[VectorStoreIndex], Optional[List[TextNode]]]:
        """
        构建或加载免签政策知识库索引

        Returns:
            (索引, 所有节点) 元组
        """
        if not AppSettings.ENABLE_VISA_FREE_FEATURE:
            logger.info("免签政策功能未启用，跳过免签知识库构建")
            return None, None

        storage_path = AppSettings.STORAGE_PATH
        kb_dir = AppSettings.VISA_FREE_KB_DIR
        hashes_file = os.path.join(storage_path, "visa_free_kb_hashes.json")

        # 确保知识库目录存在
        os.makedirs(kb_dir, exist_ok=True)

        if not any(os.scandir(kb_dir)):
            logger.warning("免签知识库文件夹为空，无法构建索引")
            return None, None

        # 检查是否需要重建索引
        if self._should_rebuild_index(storage_path, hashes_file, kb_dir, AppSettings.VISA_FREE_COLLECTION):
            return self._build_index(storage_path, kb_dir, hashes_file, AppSettings.VISA_FREE_COLLECTION)
        else:
            return self._build_index(storage_path, kb_dir, hashes_file, AppSettings.VISA_FREE_COLLECTION)

    def create_retriever(self):
        """创建通用知识库混合检索器"""
        if self.index is None or self.all_nodes is None:
            logger.error("索引或节点未初始化，无法创建检索器")
            return None

        self.retriever = RetrieverFactory.create_hybrid_retriever(
            self.index,
            self.all_nodes,
            AppSettings.RETRIEVAL_TOP_K,
            AppSettings.RETRIEVAL_TOP_K_BM25
        )
        return self.retriever

    def create_visa_free_retriever(self):
        """创建免签政策知识库混合检索器"""
        if not AppSettings.ENABLE_VISA_FREE_FEATURE:
            logger.info("免签政策功能未启用，跳过检索器创建")
            return None

        if self.visa_free_index is None or self.visa_free_nodes is None:
            logger.warning("免签索引或节点未初始化，无法创建检索器")
            return None

        self.visa_free_retriever = RetrieverFactory.create_hybrid_retriever(
            self.visa_free_index,
            self.visa_free_nodes,
            AppSettings.RETRIEVAL_TOP_K,
            AppSettings.RETRIEVAL_TOP_K_BM25
        )
        logger.info("免签政策知识库检索器创建成功")
        return self.visa_free_retriever

    def _should_rebuild_index(
        self,
        storage_path: str,
        hashes_file: str,
        kb_dir: str,
        collection_name: str
    ) -> bool:
        """判断是否需要重建索引"""
        if not os.path.exists(storage_path) or not os.path.exists(hashes_file):
            return True

        # 检查 Qdrant 集合是否存在
        try:
            collections = self.qdrant_client.get_collections().collections
            collection_exists = any(
                c.name == collection_name for c in collections
            )
            if not collection_exists:
                logger.info(f"Qdrant 集合 {collection_name} 不存在，需要重建索引")
                return True
        except Exception as e:
            logger.warning(f"无法检查 Qdrant 集合状态: {e}，将重建索引")
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

    # def _load_index(
    #     self,
    #     storage_path: str
    # ) -> Tuple[Optional[VectorStoreIndex], Optional[List[TextNode]]]:
    #     """加载已有索引"""
    #     try:
    #         logger.info("从本地加载索引...")
    #
    #         # 确保全局 Embedding 已设置
    #         if Settings.embed_model is None:
    #             raise ValueError("全局 Embed model 未设置")
    #
    #         service_context = ServiceContext.from_defaults(
    #             llm=self.llm,
    #             embed_model=Settings.embed_model
    #         )
    #
    #         storage_context = StorageContext.from_defaults(persist_dir=storage_path)
    #         index = load_index_from_storage(storage_context, service_context=service_context)
    #
    #         all_nodes = list(storage_context.docstore.docs.values())
    #         if not all_nodes:
    #             raise ValueError("未找到任何节点")
    #
    #         logger.info(f"成功加载索引，共 {len(all_nodes)} 个节点")
    #         self.index = index
    #         self.all_nodes = all_nodes
    #         return index, all_nodes
    #
    #     except Exception as e:
    #         logger.error(f"加载索引失败: {e}，将重新构建", exc_info=True)
    #         return None, None

    # 这是使用向量数据库的方法，10.17 重构
    def _load_index(
            self,
            storage_path: str
    ) -> Tuple[Optional[VectorStoreIndex], Optional[List[TextNode]]]:
        """从 Qdrant 加载索引"""
        try:
            logger.info("从 Qdrant 加载索引...")

            # 检查集合是否存在
            collections = self.qdrant_client.get_collections().collections
            collection_exists = any(
                c.name == AppSettings.QDRANT_COLLECTION for c in collections
            )

            if not collection_exists:
                logger.warning(f"集合 {AppSettings.QDRANT_COLLECTION} 不存在")
                return None, None

            # 创建向量存储
            vector_store = QdrantVectorStore(
                client=self.qdrant_client,
                collection_name=AppSettings.QDRANT_COLLECTION
            )

            # 确保全局 Embedding 已设置
            if Settings.embed_model is None:
                raise ValueError("全局 Embed model 未设置")

            service_context = ServiceContext.from_defaults(
                llm=self.llm,
                embed_model=Settings.embed_model
            )

            # 从向量存储加载索引
            index = VectorStoreIndex.from_vector_store(
                vector_store=vector_store,
                service_context=service_context
            )

            # 获取所有节点 - 修复文本加载问题，使用正确的字段名
            logger.info("正在从 Qdrant 获取所有文本节点...")
            scroll_result = self.qdrant_client.scroll(
                collection_name=AppSettings.QDRANT_COLLECTION,
                limit=10000,
                with_payload=True,
                with_vectors=False
            )

            all_nodes = []
            for point in scroll_result[0]:
                if point.payload:
                    # LlamaIndex 将文本内容存储在 _node_content 字段中，不是 text 字段
                    text_content = point.payload.get("_node_content", "")

                    # 如果 _node_content 为空，尝试备用字段
                    if not text_content:
                        text_content = point.payload.get("text", "")

                    if not text_content:
                        logger.warning(f"节点 {point.id} 缺少文本内容 (_node_content 和 text 字段都为空)")
                        continue

                    # 构造元数据，保留文件信息
                    metadata = {
                        "file_name": point.payload.get("file_name", ""),
                        "file_path": point.payload.get("file_path", ""),
                        "doc_id": point.payload.get("doc_id"),
                        "document_id": point.payload.get("document_id"),
                        "ref_doc_id": point.payload.get("ref_doc_id"),
                        "_node_type": point.payload.get("_node_type", "Document")
                    }

                    node = TextNode(
                        text=text_content,
                        id_=str(point.id),
                        metadata=metadata
                    )
                    all_nodes.append(node)

            if not all_nodes:
                logger.error("从 Qdrant 未能加载到任何有效文本节点")
                return None, None

            logger.info(f"成功加载索引,共 {len(all_nodes)} 个节点")
            self.index = index
            self.all_nodes = all_nodes
            return index, all_nodes

        except Exception as e:
            logger.error(f"加载索引失败: {e}", exc_info=True)
            logger.info("将尝试重新构建索引...")
            return None, None

    def _build_index(
        self,
        storage_path: str,
        kb_dir: str,
        hashes_file: str,
        collection_name: str
    ) -> Tuple[Optional[VectorStoreIndex], Optional[List[TextNode]]]:
        """构建新索引到 Qdrant"""
        logger.info(f"开始构建新索引: {collection_name}...")

        # 删除旧集合
        try:
            self.qdrant_client.delete_collection(
                collection_name=collection_name
            )
            logger.info(f"已删除旧集合 {collection_name}")
        except Exception as e:
            logger.info(f"无旧集合需要删除: {e}")

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

        # 创建向量存储
        vector_store = QdrantVectorStore(
            client=self.qdrant_client,
            collection_name=collection_name
        )

        # 构建索引
        logger.info("生成 Embeddings 并存储到 Qdrant...")

        storage_context = StorageContext.from_defaults(
            vector_store=vector_store
        )

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

        # 保存哈希文件(用于检测文件变化)
        os.makedirs(storage_path, exist_ok=True)
        current_hashes = DocumentProcessor.compute_file_hashes(kb_dir)
        with open(hashes_file, "w", encoding="utf-8") as f:
            json.dump(current_hashes, f, sort_keys=True)

        logger.info(f"索引构建完成,共 {len(all_nodes)} 个节点")
        self.index = index
        self.all_nodes = all_nodes
        return index, all_nodes
