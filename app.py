# -*- coding: utf-8 -*-
"""
RAG 系统主应用入口
企业级架构 - 清晰的模块化设计
"""
import os
from flask import Flask, render_template
from flask_cors import CORS
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

from config import Settings
from utils import logger
from services import LLMService, EmbeddingService, KnowledgeService, IntentClassifier
from core import LLMStreamWrapper, MultiKBRetrieverFactory
from api import JudgeHandler, KnowledgeHandler
from routes import knowledge_bp
from middleware.auth_decorator import create_auth_manager


def create_app():
    """应用工厂模式：创建并配置 Flask 应用"""

    # 计算项目根目录
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..','..'))
    template_dir = os.path.join(project_root, 'templates')
    static_dir = os.path.join(project_root, 'static')

    # 创建 Flask 应用
    app = Flask(
        __name__,
        template_folder=template_dir,
        static_folder=static_dir
    )
    CORS(app)

    # 初始化服务层
    logger.info("=" * 60)
    logger.info("开始初始化 RAG 系统...")
    logger.info("=" * 60)

    # 1. 初始化 Embedding 和 Reranker
    embedding_service = EmbeddingService()
    embed_model, reranker = embedding_service.initialize()

    # 2. 初始化 LLM 服务
    llm_service = LLMService()
    llm_clients = llm_service.initialize()

    # 3. 初始化通用知识库
    default_llm = llm_service.get_client(Settings.DEFAULT_LLM_ID)
    knowledge_service = KnowledgeService(default_llm)

    logger.info(f"使用默认模型 '{Settings.DEFAULT_LLM_ID}' 构建通用知识库索引...")
    index, all_nodes = knowledge_service.build_or_load_index()

    if index:
        context_window = index.service_context.llm.metadata.context_window
        logger.info("=" * 60)
        logger.info("【验证】通用知识库索引已创建")
        logger.info(f"【验证】内部 LLM 上下文窗口: {context_window}")
        logger.info("=" * 60)

    # 3.5 初始化免签政策知识库（如果启用）
    visa_free_index = None
    visa_free_nodes = None
    if Settings.ENABLE_VISA_FREE_FEATURE:
        logger.info("免签政策功能已启用，开始构建免签知识库...")
        visa_free_index, visa_free_nodes = knowledge_service.build_or_load_visa_free_index()
        knowledge_service.visa_free_index = visa_free_index
        knowledge_service.visa_free_nodes = visa_free_nodes
        
        if visa_free_index:
            logger.info("【验证】免签政策知识库索引已创建")
        else:
            logger.warning("免签政策知识库索引创建失败或为空")
    else:
        logger.info("免签政策功能未启用")

    # 4. 创建检索器
    retriever = None
    visa_free_retriever = None
    
    if index and all_nodes:
        retriever = knowledge_service.create_retriever()
        logger.info("通用知识库混合检索器创建成功")
    else:
        logger.error("通用知识库索引或节点加载失败")
        return None
    
    # 创建免签知识库检索器（如果启用）
    if Settings.ENABLE_VISA_FREE_FEATURE and visa_free_index and visa_free_nodes:
        visa_free_retriever = knowledge_service.create_visa_free_retriever()
        if visa_free_retriever:
            logger.info("免签政策知识库检索器创建成功")
        else:
            logger.warning("免签政策知识库检索器创建失败")

    # 4.5 初始化对话管理器（用于多轮对话功能）
    try:
        knowledge_service.initialize_conversation_manager()
        logger.info("对话管理器初始化成功 - 多轮对话功能已启用")
    except Exception as e:
        logger.warning(f"对话管理器初始化失败（多轮对话功能不可用）: {e}")
        logger.warning("单轮对话功能不受影响，将继续正常运行")

    # 5. 初始化意图分类器和多知识库检索器
    intent_classifier = None
    multi_kb_retriever = None
    
    if Settings.ENABLE_VISA_FREE_FEATURE:
        # 创建意图分类器
        intent_classifier = IntentClassifier(llm_service)
        logger.info("意图分类器初始化成功")
        
        # 创建多知识库检索器
        if visa_free_retriever:
            multi_kb_retriever = MultiKBRetrieverFactory.create_multi_kb_retriever(
                general_retriever=retriever,
                visa_free_retriever=visa_free_retriever,
                general_count=Settings.GENERAL_RETRIEVAL_COUNT,
                visa_free_count=Settings.VISA_FREE_RETRIEVAL_COUNT
            )
            logger.info("多知识库检索器初始化成功")
        else:
            logger.warning("免签检索器未创建，多知识库功能不可用")

    # 6. 初始化业务处理器
    llm_wrapper = LLMStreamWrapper()
    knowledge_handler = KnowledgeHandler(
        retriever=retriever,
        reranker=reranker,
        llm_wrapper=llm_wrapper,
        llm_service=llm_service,
        intent_classifier=intent_classifier,
        multi_kb_retriever=multi_kb_retriever
    )
    judge_handler = JudgeHandler(retriever, reranker, llm_wrapper)



    # 7. 将服务注入应用上下文
    app.llm_service = llm_service
    app.knowledge_handler = knowledge_handler
    app.judge_handler = judge_handler
    app.knowledge_service = knowledge_service  # 添加这行，让路由可以访问 conversation_manager
    app.retriever = retriever
    app.reranker = reranker

    # 🔥 7.5 初始化并注册认证管理器
    auth_manager = create_auth_manager()
    app.extensions['auth_manager'] = auth_manager
    logger.info(f"认证管理器已注册，Spring Boot URL: {os.getenv('SPRING_BOOT_URL', 'http://localhost:8080')}")

    # 8. 注册路由蓝图
    app.register_blueprint(knowledge_bp,url_prefix='/api')

    # 9. 注册页面路由
    register_page_routes(app)

    logger.info("=" * 60)
    logger.info("RAG 系统初始化完成，服务器准备就绪")
    logger.info("=" * 60)

    return app


def register_page_routes(app):
    """注册页面路由"""

    @app.route('/')
    def route_root():
        return render_template('navigation.html')

    @app.route('/knowledge')
    def route_knowledge():
        return render_template('knowledge_answer.html')



    @app.route('/board')
    def route_board():
        return render_template('feedback_list.html')

    @app.route('/viewer')
    def route_viewer():
       return render_template('feedback_viewer.html')
    @app.route('/knowledge/v4')
    def route_knowledge_v4():
        return render_template('knowledge_answer_v4.html')

    @app.route('/topic')
    def route_topic():
        return render_template('topic_answer.html')

    @app.route('/knowledge/conversation')
    def route_conversation():
        return render_template('conversation3.html')

    @app.route('/topic/v2')
    def route_topic_test():
        return render_template('test_answer.html')

    @app.route('/debug')
    def route_debug():
        return render_template('debug.html')


def main():
    """主函数"""
    app = create_app()

    if app is None:
        logger.error("应用初始化失败，无法启动服务器")
        return

    # 启动服务器
    app.run(
        host=Settings.SERVER_HOST,
        port=Settings.SERVER_PORT,
        debug=Settings.SERVER_DEBUG_MODE
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger.error(f"服务器启动失败: {e}", exc_info=True)
