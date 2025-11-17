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
from services import LLMService, EmbeddingService, KnowledgeService
from core import LLMStreamWrapper
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

    # 4. 创建检索器
    retriever = None
    
    if index and all_nodes:
        retriever = knowledge_service.create_retriever()
        logger.info("通用知识库混合检索器创建成功")
        logger.info(f"🔍 [DEBUG] 通用检索器对象ID: {id(retriever)}")
        logger.info(f"🔍 [DEBUG] 通用检索器类型: {type(retriever).__name__}")
    else:
        logger.error("通用知识库索引或节点加载失败")
        return None

    # 4.5 初始化对话管理器（用于多轮对话功能）
    try:
        knowledge_service.initialize_conversation_manager()
        logger.info("对话管理器初始化成功 - 多轮对话功能已启用")
    except Exception as e:
        logger.warning(f"对话管理器初始化失败（多轮对话功能不可用）: {e}")
        logger.warning("单轮对话功能不受影响，将继续正常运行")

    # 4.6 初始化免签知识库（可选功能）
    visa_free_retriever = None
    multi_kb_retriever = None
    intent_classifier = None
    
    if Settings.ENABLE_VISA_FREE_FEATURE:
        logger.info("=" * 60)
        logger.info("初始化免签知识库功能...")
        logger.info("=" * 60)
        
        try:
            # 构建免签知识库索引
            visa_index, visa_nodes = knowledge_service.build_or_load_visa_free_index()
            
            if visa_index and visa_nodes:
                # 创建免签检索器
                visa_free_retriever = knowledge_service.create_visa_free_retriever()
                
                if visa_free_retriever is None:
                    logger.error("免签检索器创建失败，无法启用双库检索功能")
                else:
                    logger.info("✓ 免签知识库检索器创建成功")
                    
                    # 创建双库检索器
                    from core import MultiKBRetriever
                    multi_kb_retriever = MultiKBRetriever(
                        general_retriever=retriever,
                        visa_free_retriever=visa_free_retriever,
                        strategy=Settings.DUAL_KB_STRATEGY
                    )
                    logger.info(f"✓ 双库检索器创建成功 | 策略: {Settings.DUAL_KB_STRATEGY}")
                    
                    # 创建意图分类器（如果启用）
                    if Settings.ENABLE_INTENT_CLASSIFIER:
                        from core import IntentClassifier
                        classifier_llm = llm_service.get_client(Settings.INTENT_CLASSIFIER_LLM_ID)
                        intent_classifier = IntentClassifier(classifier_llm)
                        logger.info("✓ 意图分类器创建成功")
                    else:
                        logger.info("⊘ 意图分类器未启用（将使用默认策略）")
                
                logger.info("=" * 60)
                logger.info("免签知识库功能初始化完成")
                logger.info("=" * 60)
            else:
                logger.warning("免签知识库为空或构建失败，免签功能不可用")
                
        except Exception as e:
            logger.error(f"免签知识库初始化失败: {e}", exc_info=True)
            logger.warning("将继续使用通用知识库")
    else:
        logger.info("免签知识库功能未启用")

    # 4.5 初始化航司知识库（可选）
    airline_retriever = None
    if Settings.ENABLE_AIRLINE_FEATURE:
        logger.info("=" * 60)
        logger.info("初始化航司知识库功能...")
        logger.info("=" * 60)
        
        try:
            # 构建航司知识库索引
            airline_index, airline_nodes = knowledge_service.build_or_load_airline_index()
            
            if airline_index and airline_nodes:
                # 创建航司检索器
                airline_retriever = knowledge_service.create_airline_retriever()
                
                if airline_retriever is None:
                    logger.error("航司检索器创建失败")
                else:
                    logger.info("✓ 航司知识库检索器创建成功")
                    
                    # 更新多库检索器，添加航司库支持
                    if multi_kb_retriever:
                        logger.info("更新多库检索器，添加航司库支持...")
                        from core import MultiKBRetriever
                        multi_kb_retriever = MultiKBRetriever(
                            general_retriever=retriever,
                            visa_free_retriever=visa_free_retriever,
                            airline_retriever=airline_retriever,
                            strategy=Settings.DUAL_KB_STRATEGY
                        )
                        logger.info("✓ 三库检索器创建成功（通用库 + 免签库 + 航司库）")
                    else:
                        # 如果没有免签库，创建双库检索器（通用 + 航司）
                        from core import MultiKBRetriever
                        multi_kb_retriever = MultiKBRetriever(
                            general_retriever=retriever,
                            visa_free_retriever=None,
                            airline_retriever=airline_retriever,
                            strategy=Settings.DUAL_KB_STRATEGY
                        )
                        logger.info("✓ 双库检索器创建成功（通用库 + 航司库）")
                
                logger.info("=" * 60)
                logger.info("航司知识库功能初始化完成")
                logger.info("=" * 60)
            else:
                logger.warning("航司知识库为空或构建失败，航司功能不可用")
                
        except Exception as e:
            logger.error(f"航司知识库初始化失败: {e}", exc_info=True)
            logger.warning("将继续使用现有知识库")
    else:
        logger.info("航司知识库功能未启用")

    # 4.7 初始化子问题分解器（可选功能）
    sub_question_decomposer = None
    if Settings.ENABLE_SUBQUESTION_DECOMPOSITION:
        logger.info("=" * 60)
        logger.info("初始化子问题分解器...")
        logger.info("=" * 60)
        
        try:
            sub_question_decomposer = knowledge_service.create_sub_question_decomposer(
                llm_service=llm_service,
                reranker=reranker
            )
            
            if sub_question_decomposer:
                logger.info("=" * 60)
                logger.info("子问题分解器初始化完成")
                logger.info("=" * 60)
            else:
                logger.warning("子问题分解器创建失败")
                
        except Exception as e:
            logger.error(f"子问题分解器初始化失败: {e}", exc_info=True)
            logger.warning("将继续使用标准检索流程")
    else:
        logger.info("子问题分解功能未启用")

    # 5. 初始化业务处理器
    llm_wrapper = LLMStreamWrapper()
    knowledge_handler = KnowledgeHandler(
        retriever=retriever,
        reranker=reranker,
        llm_wrapper=llm_wrapper,
        llm_service=llm_service,
        # 多知识库相关组件（可选）
        visa_free_retriever=visa_free_retriever,
        airline_retriever=airline_retriever,
        multi_kb_retriever=multi_kb_retriever,
        intent_classifier=intent_classifier,
        # 子问题分解器（可选）
        sub_question_decomposer=sub_question_decomposer
    )
    judge_handler = JudgeHandler(retriever, reranker, llm_wrapper)



    # 6. 将服务注入应用上下文
    app.llm_service = llm_service
    app.knowledge_handler = knowledge_handler
    app.judge_handler = judge_handler
    app.knowledge_service = knowledge_service  # 添加这行，让路由可以访问 conversation_manager
    app.retriever = retriever
    app.reranker = reranker

    # 🔥 6.5 初始化并注册认证管理器
    auth_manager = create_auth_manager()
    app.extensions['auth_manager'] = auth_manager
    logger.info(f"认证管理器已注册，Spring Boot URL: {os.getenv('SPRING_BOOT_URL', 'http://localhost:8080')}")

    # 7. 注册路由蓝图
    app.register_blueprint(knowledge_bp,url_prefix='/api')

    # 8. 注册页面路由
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
