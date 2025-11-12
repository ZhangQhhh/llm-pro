#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
规则知识库构建脚本
从 prompts.py 中提取特殊规定，并创建规则文档
"""
import os
import sys

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import Settings
from utils.logger import logger


def create_rules_documents():
    """创建规则知识库文档"""
    
    logger.info("=" * 60)
    logger.info("规则知识库文档生成")
    logger.info("=" * 60)
    
    # 1. 创建规则知识库目录
    rules_kb_dir = Settings.RULES_KB_DIR
    
    logger.info(f"\n[步骤1] 创建规则知识库目录")
    logger.info(f"目录路径: {rules_kb_dir}")
    
    try:
        os.makedirs(rules_kb_dir, exist_ok=True)
        logger.info("✓ 目录创建成功")
    except Exception as e:
        logger.error(f"✗ 目录创建失败: {e}")
        return False
    
    # 2. 创建特殊规定文档
    logger.info(f"\n[步骤3] 创建特殊规定文档")
    
    special_rules_part1 = """【特殊规定】第1-5条

## 特殊规定1：JS计数器规则
以JS0只有在国内赴港出境时候扣减次数、JS1只有在国内出境时候赴澳扣减次数，JS2只有港方入境时候扣减次数，JS3只有澳方入境时候扣减次数，为前提分析。

JS2初始状态等于JS0，JS1初始状态等于JS4。签注计数器初始状态等于签发次数，例如签发一次有效赴澳门签注，JS1=JS4=1。例如两次有效赴港签注，JS0=JS2=2。

## 特殊规定2：出入境手续办理规则
出入境手续办理只有边检机关可以办理，地方公安无法办理手续，且出入境手续办理只能且仅能在一个护照上办理。为前提回答。

## 特殊规定3：随身携带与封存的区别
请注意区分随身携带和封存的区别，两者不是一回事，不能随身携带的要按照是否可以封存处理。

## 特殊规定4：审批权限规则
各级领导、机关对属于本级职权范围的，应当直接作出决定，不必请示上级机关。对超出本规范规定的审批权限事项或其他认为有必要向上级请示的事项，应当按照规定流程和要求向上级请示。

## 特殊规定5：章类默认规则
出现的任何章如果未特别提及详细章类，全部默认为验讫章。
"""
    
    special_rules_part2 = """【特殊规定】第6-10条

## 特殊规定6：免签政策冲突处理
当一个国家多种免签政策冲突或者矛盾时候，选用最优最长时限的免签政策实施。

## 特殊规定7：军舰检查规则
军舰不进行船体检查包括为不查验船所运载的枪支弹药或其他武器，此为特殊情况，不受其他因素影响。

## 特殊规定8：船舶国籍变更规则
船舶国籍变更，船舶英文名、船舶中文名可继续延用。

## 特殊规定9：人证对照次数
边检机关按要求对船员和其他出入境人员至少进行2次人证对照，第一次为入境时，第二次为出境时。

## 特殊规定10：行政职务名称匹配规则
在回答问题中，行政职务名称必须完全相等才算正确，否则不正确。
"""
    
    special_rules_part3 = """【特殊规定】第11-15条

## 特殊规定11：邮轮免签政策优先级
邮轮免签入境政策和其他免签政策冲突时候，优先适用停留时间最长的免签政策。

## 特殊规定12：民警身份类别
领导不属于民警身份类别。民警指普通民警，不包含领导。

## 特殊规定13：法定不予签发出入境证件人员

具有以下情形之一的人员可报备为法定不予签发出入境证件人员：

1. 被判处刑罚尚未执行完毕或者属于刑事案件被告人、犯罪嫌疑人的；
2. 有未了结的民事案件，人民法院决定不准出境的；
3. 因妨害国(边)境管理受到刑事处罚或者因非法出境、非法居留、非法就业被其他国家或者地区遣返，未满不准出境规定年限的；
4. 可能危害国家安全和利益，国务院有关主管部门决定不准出境的；
5. 恐怖活动人员和恐怖活动嫌疑人员；
6. 涉嫌间谍行为或者其他危害国家安全行为的人员；
7. 有关机关认为涉密人员出境将对国家安全造成危害或者对国家利益造成重大损失的；
8. 可能逃往境外的被审查调查人以及涉案人员等相关人员；
9. 有服兵役义务的公民拒绝、逃避征集并经县级人民政府责令限期改正后仍拒不改正的；
10. 受海关处罚的当事人或者其法定代表人、主要负责人，在出境前未缴清罚款、违法所得和依法追缴的货物、物品、走私运输工具的等值价款，又不提担保的，海关通知不准出境的；
11. 欠缴税款的纳税人或者其法定代表人既未结清税款、滞纳金，又不提供担保，税务机关通知不准出境的；
12. 具有法律、行政法规规定不准出境的其他情形的人员。
"""
    
    # 3. 写入文件
    documents = [
        ("01_特殊规定_第1-5条.txt", special_rules_part1),
        ("02_特殊规定_第6-10条.txt", special_rules_part2),
        ("03_特殊规定_第11-15条.txt", special_rules_part3),
    ]
    
    created_count = 0
    for filename, content in documents:
        file_path = os.path.join(rules_kb_dir, filename)
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            logger.info(f"✓ 创建文档: {filename}")
            created_count += 1
        except Exception as e:
            logger.error(f"✗ 创建文档失败 {filename}: {e}")
    
    # 4. 创建 README
    readme_path = os.path.join(rules_kb_dir, "README.md")
    readme_content = """# 规则知识库 - 特殊规定

## 说明
此目录用于存放特殊规定文档。这些规则会在每次回答时自动注入到上下文中。

**注意**：证据链验证规范和不确定性判定机制已保留在 System Prompt 中，此库只管理特殊规定。

## 文档类型

### 特殊规定
- JS计数器规则
- 出入境手续办理规则
- 免签政策冲突处理
- 船舶国籍变更规则
- 行政职务名称匹配规则
- 法定不予签发出入境证件人员
- 其他业务场景特殊规则

## 使用方法
1. 将特殊规定文档放入此目录
2. 启动应用时会自动构建索引
3. 每次回答时会自动检索并注入相关规则（固定注入3条）

## 注意事项
- 规则文档应使用清晰的标题和结构
- 每个规则应包含：规则编号、规则内容、适用场景
- 文档更新后需要重启应用以重建索引
- 规则优先级：特殊规定 > 业务规定 > 通识知识

## 文档格式
支持的格式：
- .txt (纯文本，推荐)
- .md (Markdown)

## 规则编号
- 特殊规定1-5：基础业务规则（JS计数器、出入境手续等）
- 特殊规定6-10：政策冲突处理规则
- 特殊规定11-15：特殊情形规则
"""
    
    try:
        with open(readme_path, 'w', encoding='utf-8') as f:
            f.write(readme_content)
        logger.info(f"\n✓ README 创建成功: {readme_path}")
    except Exception as e:
        logger.warning(f"✗ README 创建失败: {e}")
    
    logger.info("\n" + "=" * 60)
    logger.info("规则知识库文档生成完成")
    logger.info("=" * 60)
    logger.info(f"\n成功创建 {created_count} 个特殊规定文档")
    logger.info(f"规则库目录: {rules_kb_dir}")
    logger.info("\n说明:")
    logger.info("- 证据链验证规范和不确定性判定机制已保留在 System Prompt 中")
    logger.info("- 此规则库只管理特殊规定（特殊规定1-19）")
    logger.info("\n下一步:")
    logger.info("1. 检查生成的特殊规定文档")
    logger.info("2. 根据需要添加更多特殊规定")
    logger.info("3. 启动应用构建规则索引")
    
    return True


if __name__ == "__main__":
    success = create_rules_documents()
    sys.exit(0 if success else 1)
