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
from core.custom_qdrant_store import FixedQdrantVectorStore
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
        
        # 免签知识库（完全独立）
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
            logger.info("[通用知识库] 检测到文件变化，重建索引...")
            index, nodes = self._build_index(storage_path, kb_dir, hashes_file, AppSettings.QDRANT_COLLECTION)
        else:
            logger.info("[通用知识库] 文件未变化，从缓存加载索引...")
            index, nodes = self._load_index(storage_path, AppSettings.QDRANT_COLLECTION)
            if index is None or nodes is None:
                logger.warning("[通用知识库] 缓存加载失败，回退到重建索引")
                index, nodes = self._build_index(storage_path, kb_dir, hashes_file, AppSettings.QDRANT_COLLECTION)
        
        # 注意：_build_index() 已经设置了 self.index 和 self.all_nodes
        # 这里直接返回即可，保持向后兼容
        return index, nodes


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

  

    # 这是使用向量数据库的方法，10.17 重构
    def _load_index(
            self,
            storage_path: str,
            collection_name: str
    ) -> Tuple[Optional[VectorStoreIndex], Optional[List[TextNode]]]:
        """从 Qdrant 加载索引（修复版：保留完整节点信息）"""
        try:
            logger.info(f"从 Qdrant 加载索引: {collection_name}...")

            # 检查集合是否存在
            collections = self.qdrant_client.get_collections().collections
            collection_exists = any(
                c.name == collection_name for c in collections
            )

            if not collection_exists:
                logger.warning(f"集合 {collection_name} 不存在")
                return None, None

            # 创建向量存储（使用修复版）
            vector_store = FixedQdrantVectorStore(
                client=self.qdrant_client,
                collection_name=collection_name
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

            # 获取所有节点 - 关键修复：保留完整的节点信息，避免重排序得分偏低
            logger.info("正在从 Qdrant 获取所有文本节点（完整信息）...")
            scroll_result = self.qdrant_client.scroll(
                collection_name=collection_name,
                limit=10000,
                with_payload=True,
                with_vectors=False  # 不需要向量，节省内存
            )

            all_nodes = []
            for point in scroll_result[0]:
                if point.payload:
                    # LlamaIndex 将文本内容存储在 _node_content 字段中
                    text_content = point.payload.get("_node_content", "")

                    # 如果 _node_content 为空，尝试备用字段
                    if not text_content:
                        text_content = point.payload.get("text", "")

                    if not text_content:
                        logger.warning(f"节点 {point.id} 缺少文本内容")
                        continue

                    # 关键修复：只保留业务元数据字段，过滤掉内部字段
                    # 避免将 Qdrant 内部字段（如 id_, embedding 等）加入 metadata
                    metadata = {}
                    for key, value in point.payload.items():
                        # 只保留不以 _ 开头的业务字段（如 file_name, file_path）
                        # 跳过所有以 _ 开头的内部字段
                        if not key.startswith("_"):
                            metadata[key] = value

                    # 构造完整的 TextNode
                    node = TextNode(
                        text=text_content,
                        id_=str(point.id),
                        metadata=metadata,
                        # 保留节点类型信息
                        excluded_embed_metadata_keys=point.payload.get("excluded_embed_metadata_keys", []),
                        excluded_llm_metadata_keys=point.payload.get("excluded_llm_metadata_keys", [])
                    )
                    all_nodes.append(node)

            logger.info(f"✓ 从 Qdrant 加载索引成功: {collection_name}，共 {len(all_nodes)} 个节点")
            
            # 根据 collection_name 设置对应的实例变量
            if collection_name == AppSettings.QDRANT_COLLECTION:
                self.index = index
                self.all_nodes = all_nodes
            elif collection_name == AppSettings.VISA_FREE_COLLECTION:
                self.visa_free_index = index
                self.visa_free_nodes = all_nodes
            elif collection_name == AppSettings.AIRLINE_COLLECTION:
                self.airline_index = index
                self.airline_nodes = all_nodes
            elif collection_name == AppSettings.RULES_COLLECTION:
                self.rules_index = index
                self.rules_nodes = all_nodes
            
            return index, all_nodes

        except Exception as e:
            logger.error(f"从 Qdrant 加载索引失败: {e}")
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
        split_docs = self.doc_processor.split_documents(docs)
        if not split_docs:
            logger.warning("文档切分后未产生有效节点")
            return None, None
        
        # ⭐ 关键修复：将 Document 转换为 TextNode
        # Document 对象会被序列化成 JSON 字符串，导致 _node_content 存储错误
        # TextNode 对象会正确提取 text 字段存储
        all_nodes = []
        for doc in split_docs:
            text_node = TextNode(
                text=doc.get_content(),
                metadata=doc.metadata.copy()
            )
            all_nodes.append(text_node)
        
        logger.info(f"已将 {len(split_docs)} 个 Document 转换为 TextNode")

        # 创建向量存储（使用修复版）
        vector_store = FixedQdrantVectorStore(
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

    # ==================== 免签知识库方法 ====================
    
    def build_or_load_visa_free_index(self) -> Tuple[Optional[VectorStoreIndex], Optional[List[TextNode]]]:
        """
        构建或加载免签知识库索引（完全独立的流程）
        
        Returns:
            (索引, 所有节点) 元组
        """
        if not AppSettings.ENABLE_VISA_FREE_FEATURE:
            logger.info("免签功能未启用，跳过免签知识库构建")
            return None, None
        
        storage_path = AppSettings.VISA_FREE_STORAGE_PATH
        kb_dir = AppSettings.VISA_FREE_KB_DIR
        hashes_file = os.path.join(storage_path, "visa_free_kb_hashes.json")
        collection_name = AppSettings.VISA_FREE_COLLECTION
        
        logger.info("=" * 60)
        logger.info("开始构建/加载免签知识库")
        logger.info(f"知识库目录: {kb_dir}")
        logger.info(f"Collection: {collection_name}")
        logger.info("=" * 60)
        
        # 确保知识库目录存在
        os.makedirs(kb_dir, exist_ok=True)
        
        if not any(os.scandir(kb_dir)):
            logger.warning("免签知识库文件夹为空，无法构建索引")
            return None, None
        
        # 检查是否需要重建索引
        if self._should_rebuild_index(storage_path, hashes_file, kb_dir, collection_name):
            logger.info("[免签知识库] 检测到文件变化，重建索引...")
            index, nodes = self._build_index(storage_path, kb_dir, hashes_file, collection_name)
        else:
            logger.info("[免签知识库] 文件未变化，从缓存加载索引...")
            index, nodes = self._load_index(storage_path, collection_name)
            if index is None or nodes is None:
                logger.warning("[免签知识库] 缓存加载失败，回退到重建索引")
                index, nodes = self._build_index(storage_path, kb_dir, hashes_file, collection_name)
        
        # 重要：将免签库的索引和节点保存到专用的实例变量
        if index and nodes:
            self.visa_free_index = index
            self.visa_free_nodes = nodes
            logger.info(f"✓ 免签知识库实例变量已设置 | 节点数: {len(nodes)}")
        
        return index, nodes
    
    def create_visa_free_retriever(self):
        """创建免签知识库混合检索器（完全独立）"""
        if not AppSettings.ENABLE_VISA_FREE_FEATURE:
            logger.info("免签功能未启用，跳过免签检索器创建")
            return None
        
        if self.visa_free_index is None or self.visa_free_nodes is None:
            logger.error("免签索引或节点未初始化，无法创建检索器")
            return None
        
        logger.info("创建免签知识库混合检索器...")
        self.visa_free_retriever = RetrieverFactory.create_hybrid_retriever(
            self.visa_free_index,
            self.visa_free_nodes,
            AppSettings.VISA_FREE_RETRIEVAL_TOP_K,
            AppSettings.VISA_FREE_RETRIEVAL_TOP_K_BM25
        )
        logger.info("✓ 免签检索器创建成功")
        return self.visa_free_retriever
    
    # ==================== 航司知识库方法 ====================
    
    def build_or_load_airline_index(self) -> Tuple[Optional[VectorStoreIndex], Optional[List[TextNode]]]:
        """
        构建或加载航司知识库索引（完全独立的流程）
        
        Returns:
            (索引, 所有节点) 元组
        """
        if not AppSettings.ENABLE_AIRLINE_FEATURE:
            logger.info("航司功能未启用，跳过航司知识库构建")
            return None, None
        
        storage_path = AppSettings.AIRLINE_STORAGE_PATH
        kb_dir = AppSettings.AIRLINE_KB_DIR
        hashes_file = os.path.join(storage_path, "airline_kb_hashes.json")
        collection_name = AppSettings.AIRLINE_COLLECTION
        
        logger.info("=" * 60)
        logger.info("开始构建/加载航司知识库")
        logger.info(f"知识库目录: {kb_dir}")
        logger.info(f"Collection: {collection_name}")
        logger.info("=" * 60)
        
        # 确保知识库目录存在
        os.makedirs(kb_dir, exist_ok=True)
        
        if not any(os.scandir(kb_dir)):
            logger.warning("航司知识库文件夹为空，无法构建索引")
            return None, None
        
        # 检查是否需要重建索引
        if self._should_rebuild_index(storage_path, hashes_file, kb_dir, collection_name):
            logger.info("[航司知识库] 检测到文件变化，重建索引...")
            index, nodes = self._build_index(storage_path, kb_dir, hashes_file, collection_name)
        else:
            logger.info("[航司知识库] 文件未变化，从缓存加载索引...")
            index, nodes = self._load_index(storage_path, collection_name)
            if index is None or nodes is None:
                logger.warning("[航司知识库] 缓存加载失败，回退到重建索引")
                index, nodes = self._build_index(storage_path, kb_dir, hashes_file, collection_name)
        
        # 重要：将航司库的索引和节点保存到专用的实例变量
        if index and nodes:
            self.airline_index = index
            self.airline_nodes = nodes
            logger.info(f"✓ 航司知识库实例变量已设置 | 节点数: {len(nodes)}")
        
        return index, nodes
    
    def create_airline_retriever(self):
        """创建航司知识库混合检索器（完全独立）"""
        if not AppSettings.ENABLE_AIRLINE_FEATURE:
            logger.info("航司功能未启用，跳过航司检索器创建")
            return None
        
        if self.airline_index is None or self.airline_nodes is None:
            logger.error("航司索引或节点未初始化，无法创建检索器")
            return None
        
        logger.info("创建航司知识库混合检索器...")
        self.airline_retriever = RetrieverFactory.create_hybrid_retriever(
            self.airline_index,
            self.airline_nodes,
            AppSettings.AIRLINE_RETRIEVAL_TOP_K,
            AppSettings.AIRLINE_RETRIEVAL_TOP_K_BM25
        )
        logger.info("✓ 航司检索器创建成功")
        return self.airline_retriever
