import os
import json
import re
from pathlib import Path
from typing import Dict, List, Optional
from .config import (
    DEEPSEEK_API_KEY,
    DEEPSEEK_BASE_URL,
    MODEL_NAME,
    MAX_TOKENS,
    TEMPERATURE,
    DASHSCOPE_API_KEY,
)
from memory_system.sliding_window import SlidingWindowMemory
from memory_system.entity_state import EntityStateTracker
from memory_system.hierarchical_summary import HierarchicalSummarizer
from memory_system.long_term_memory import LongTermEventMemory
from memory_system.character_relationship import CharacterRelationshipGraph
# Enhanced continuity evaluator (the active scorer for this generator)
from evaluation.continuity_v2 import EnhancedContinuityEvaluator
from .llm_client import LLMClient
from .chapter_analyzer import ChapterAnalyzer, apply_analysis_to_memory
from .background_task import ChapterPostProcessor


class NovelGenerator:
    """
    核心小说生成器
    整合四个记忆模块，实现完整的生成工作流
    """

    def __init__(self, topic_dir: str = "results", enable_multimedia: bool = False):
        """
        初始化小说生成器
        
        Args:
            topic_dir: 主题目录路径
            enable_multimedia: 是否启用多媒体功能
        """
        # 初始化五个记忆模块
        self.sliding_window = SlidingWindowMemory(memory_dir=topic_dir)
        self.entity_state = EntityStateTracker(memory_dir=topic_dir)
        self.hierarchical_summary = HierarchicalSummarizer(memory_dir=topic_dir)
        self.long_term_memory = LongTermEventMemory(memory_dir=topic_dir)
        self.character_relationship = CharacterRelationshipGraph(memory_dir=topic_dir)

        # API 配置
        self.api_key = DEEPSEEK_API_KEY
        self.base_url = DEEPSEEK_BASE_URL
        self.model_name = MODEL_NAME
        self.max_tokens = MAX_TOKENS
        self.temperature = TEMPERATURE
        self.dashscope_api_key = DASHSCOPE_API_KEY

        # 初始化 LLM 客户端（使用 OpenAI SDK）
        self.llm_client = LLMClient(
            api_key=self.api_key,
            base_url=self.base_url,
            model_name=self.model_name,
            max_tokens=self.max_tokens,
            temperature=self.temperature
        )

        # 多媒体功能配置
        self.enable_multimedia = enable_multimedia
        if self.enable_multimedia and self.dashscope_api_key:
            from multimedia.multimedia_manager import MultimediaManager
            self.multimedia_manager = MultimediaManager(api_key=self.dashscope_api_key)
        else:
            self.multimedia_manager = None

        # 章节分析器（LLM 驱动）
        self.chapter_analyzer = ChapterAnalyzer(self.llm_client)

        # 后台任务处理器
        self.post_processor = ChapterPostProcessor(self)

        # Initialize enhanced continuity evaluator
        self.continuity_evaluator = EnhancedContinuityEvaluator(
            llm_client=self.llm_client,
            strictness=0.7
        )

        # 确保结果目录存在并验证路径安全
        self.topic_dir = self._safe_path(topic_dir)
        os.makedirs(self.topic_dir, exist_ok=True)
    
    def _safe_path(self, path: str) -> str:
        """
        验证并返回安全的路径，防止路径遍历攻击

        Args:
            path: 输入路径

        Returns:
            str: 安全的路径

        Raises:
            ValueError: 如果路径不安全
        """
        project_root = Path(__file__).parent.resolve()
        safe = Path(path).resolve()

        # 检查是否在项目目录内（使用真实的路径包含判断，避免同前缀的兄弟目录绕过）
        if not self._is_within(safe, project_root):
            # 尝试作为相对路径处理
            safe = (project_root / path).resolve()
            # 再次验证
            if not self._is_within(safe, project_root):
                raise ValueError(f"不安全的路径：{path}")

        return str(safe)

    @staticmethod
    def _is_within(child: Path, parent: Path) -> bool:
        """
        判断 child 是否位于 parent 目录内（含 parent 本身）

        使用 Path.relative_to 进行真实的层级判断，避免
        str.startswith 带来的同前缀兄弟目录绕过（例如
        project_root 与 project_root_evil）。
        """
        try:
            child.relative_to(parent)
            return True
        except ValueError:
            return False

    def generate_next_chapter(self, chapter_title: str, custom_prompt: str = "") -> str:
        """
        生成下一章节
        
        Args:
            chapter_title: 章节标题
            custom_prompt: 自定义提示词
            
        Returns:
            str: 生成的章节内容
        """
        if not self.api_key:
            raise ValueError("请先配置 DEEPSEEK_API_KEY（通过前端设置页面或 .env 文件）")

        # 构建完整提示词
        full_prompt = self._build_full_prompt(custom_prompt)

        # 调用 API 生成内容
        response = self._call_api(full_prompt)

        if response:
            # 更新滑动窗口
            self.sliding_window.add_content(chapter_title, response)

            # 保存章节到文件
            self._save_chapter(chapter_title, response)

            # 获取章节号
            chapter_num = len([
                f for f in os.listdir(self.topic_dir)
                if f.startswith("chapter_") and f.endswith(".txt")
            ])

            # 使用 LLM 分析章节并更新记忆系统
            self.analyze_and_update_memory(chapter_num, chapter_title, response)

            return response
        else:
            return ""

    def generate_next_chapter_with_continuity_check(
        self,
        chapter_title: str,
        custom_prompt: str = "",
        continuity_threshold: float = 80.0
    ) -> str:
        """
        生成下一章节并进行连续性检查
        如果连续性分数低于阈值，则优化内容

        Uses the EnhancedContinuityEvaluator for multi-dimensional analysis

        Args:
            chapter_title: 章节标题
            custom_prompt: 自定义提示词
            continuity_threshold: 连续性评分阈值 (0-100)

        Returns:
            str: 生成的章节内容
        """
        if not self.api_key:
            raise ValueError("请先配置 DEEPSEEK_API_KEY（通过前端设置页面或 .env 文件）")

        # 获取前一章内容（如果存在）
        previous_chapter = self._get_previous_chapter_content()

        # 构建完整提示词
        full_prompt = self._build_full_prompt(custom_prompt)

        # 调用 API 生成内容
        response = self._call_api(full_prompt)

        if response:
            if previous_chapter:
                # Build memory context for enhanced evaluation
                memory_context = self._build_memory_context()

                # Use enhanced continuity evaluator
                continuity_score = self.continuity_evaluator.evaluate(
                    previous_context=previous_chapter,
                    new_content=response,
                    memory_context=memory_context
                )

                # Convert to 0-100 scale
                score_percent = continuity_score.overall_score * 100

                print(f"章节连续性评分：{score_percent:.2f}")
                print(f"维度评分：{continuity_score.dimension_scores}")

                if continuity_score.issues:
                    print(f"检测到 {len(continuity_score.issues)} 个连续性问题:")
                    for issue in continuity_score.issues:
                        print(f"  [{issue.severity}] {issue.dimension.value}: {issue.description}")

                # Save evaluation results
                self._save_evaluation_result(continuity_score)

                if score_percent < continuity_threshold:
                    print(f"连续性评分低于阈值 ({continuity_threshold})，正在优化内容...")

                    # Generate fix prompt using the enhanced evaluator
                    # 传入前一章上下文，使优化器知道需要与什么衔接
                    fix_prompt = self.continuity_evaluator.generate_fix_prompt(
                        continuity_score, response, previous_context=previous_chapter
                    )
                    optimized_content = self.llm_client.generate(fix_prompt)

                    if optimized_content:
                        # Re-evaluate optimized content
                        optimized_score = self.continuity_evaluator.evaluate(
                            previous_chapter, optimized_content, memory_context
                        )
                        print(f"优化后连续性评分：{optimized_score.overall_score * 100:.2f}")
                        final_content = optimized_content
                    else:
                        print("优化失败，使用原始内容")
                        final_content = response
                else:
                    print("连续性评分达标，接受生成的内容")
                    final_content = response
            else:
                # 如果没有前一章，则直接使用生成的内容
                final_content = response

            # 更新滑动窗口
            self.sliding_window.add_content(chapter_title, final_content)

            # 保存章节到文件
            self._save_chapter(chapter_title, final_content)

            # 获取章节号
            chapter_num = len([
                f for f in os.listdir(self.topic_dir)
                if f.startswith("chapter_") and f.endswith(".txt")
            ])

            # 使用 LLM 分析章节并更新记忆系统
            self.analyze_and_update_memory(chapter_num, chapter_title, final_content)

            return final_content
        else:
            return ""

    def _build_memory_context(self) -> Dict:
        """
        Build memory context for continuity evaluation

        Returns:
            Dict: Memory context containing characters, relationships, and recent events
        """
        context = {}

        # 角色状态：EntityStateTracker 将角色存放在 entities['characters'] 下，
        # 并没有 .characters 属性（旧代码的 hasattr 检查恒为 False）。
        characters = self.entity_state.entities.get('characters', {})
        if characters:
            context['characters'] = characters

        # 角色关系：CharacterRelationshipGraph 以嵌套字典 self.relationships 存储，
        # 并没有 to_dict 方法（旧代码的 hasattr 检查恒为 False）。
        relationships = getattr(self.character_relationship, 'relationships', None)
        if relationships:
            context['relationships'] = relationships

        # 近期事件：get_context 已按 token 限制截断，无需再按字符二次截断
        recent_content = self.sliding_window.get_context(max_tokens=500)
        if recent_content:
            context['recent_events'] = recent_content

        return context

    def _save_evaluation_result(self, score):
        """
        Save evaluation result to file for analysis

        Args:
            score: ContinuityScore object
        """
        try:
            results_file = os.path.join(self.topic_dir, "evaluation_results.json")

            # Load existing results
            results = []
            if os.path.exists(results_file):
                with open(results_file, 'r', encoding='utf-8') as f:
                    results = json.load(f)

            # Add new result
            results.append({
                "timestamp": score.metadata.get("timestamp", ""),
                "overall_score": score.overall_score,
                "dimension_scores": score.dimension_scores,
                "issues_count": len(score.issues),
                "critical_issues": len([i for i in score.issues if i.severity == "critical"]),
                "method": score.metadata.get("method", "unknown")
            })

            # Save
            with open(results_file, 'w', encoding='utf-8') as f:
                json.dump(results, f, ensure_ascii=False, indent=2)

        except Exception as e:
            print(f"保存评估结果失败：{e}")

    def _get_previous_chapter_content(self) -> str:
        """
        获取前一章的内容
        
        Returns:
            str: 前一章内容
        """
        # 获取最新的章节文件
        chapter_files = [
            f for f in os.listdir(self.topic_dir) 
            if f.startswith("chapter_") and f.endswith(".txt")
        ]
        if not chapter_files:
            return ""

        # 按文件名排序，获取最新的章节
        chapter_files.sort()
        latest_chapter_file = chapter_files[-1]

        with open(os.path.join(self.topic_dir, latest_chapter_file), 'r', encoding='utf-8') as f:
            content = f.read()

        # 移除标题部分，只返回正文
        lines = content.split('\n')
        for i, line in enumerate(lines):
            if line.strip() == "":
                return '\n'.join(lines[i+1:]).strip()

        return content.strip()

    def _build_full_prompt(self, custom_prompt: str = "", max_tokens: int = 6000) -> str:
        """
        构建完整的提示词，包含四个记忆模块的内容
        实现 Token 自适应动态缩减策略

        Args:
            custom_prompt: 自定义提示词
            max_tokens: 最大 Token 数阈值（默认 6000，预留空间给响应）

        Returns:
            str: 完整的提示词
        """
        # 优先级配置（数字越小优先级越低，越容易被缩减）
        # 1=最先被缩减，5=最后被缩减
        PRIORITY = {
            'rag': 1,              # RAG 检索结果 - 最先被缩减
            'sliding_window': 2,   # 滑动窗口 - 第二被缩减
            'hierarchy': 3,        # 层级摘要 - 第三被缩减
            'entities': 4,         # 实体状态 - 最后被缩减
        }
        
        # 缩减比例配置
        REDUCE_RATIO = {
            'rag': 0.7,            # 每次缩减到 70%
            'sliding_window': 0.8,
            'hierarchy': 0.8,
            'entities': 0.9,
        }
        
        # 初始配置
        rag_top_k = 5              # RAG 检索数量
        sliding_window_chars = 3000  # 滑动窗口字符数
        hierarchy_levels = 3       # 层级摘要层数
        entity_max_count = 50      # 实体最大数量
        
        # 构建初始提示词
        def build_prompt():
            prompt_parts = []
            
            # 1. 添加实体状态信息
            entity_text = self.entity_state.to_text_description(max_count=entity_max_count)
            if entity_text:
                prompt_parts.append(entity_text)
            
            # 1.5. 添加角色关系信息
            relationship_text = self.character_relationship.to_text_description()
            if relationship_text:
                prompt_parts.append(relationship_text)
            
            # 2. 添加层级摘要信息
            hierarchy_text = self.hierarchical_summary.get_hierarchical_context(max_levels=hierarchy_levels)
            if hierarchy_text:
                prompt_parts.append(hierarchy_text)
            
            # 3. 获取当前活跃实体（从滑动窗口的最新内容中提取）
            recent_content = self.sliding_window.get_context(max_chars=sliding_window_chars)
            active_entities = self._extract_entities_from_text(recent_content)
            
            # 4. 添加长期记忆检索结果
            if active_entities:
                relevant_events = self.long_term_memory.get_context_by_entities(
                    active_entities, top_k=rag_top_k
                )
                rag_context = self.long_term_memory.to_context_format(relevant_events)
                prompt_parts.append(rag_context)
            
            # 5. 添加近期正文（滑动窗口内容）
            if recent_content:
                prompt_parts.append(f"[近期正文]:\n{recent_content}")
            
            # 6. 添加自定义提示词（如果有的话）
            if custom_prompt:
                prompt_parts.append(f"[自定义指令]: {custom_prompt}")
            
            # 7. 添加最终指令
            prompt_parts.append(
                "[指令]: 请基于以上设定、摘要和前文，续写接下来的剧情，要求符合人物当前状态，"
                "且自然推进当前主线。保持文风一致，情节连贯，避免逻辑错误。"
                "输出纯正文内容，不要包含章节标题。"
            )
            
            return "\n\n".join(prompt_parts)
        
        # 构建初始提示词并计算 Token 数
        prompt = build_prompt()
        prompt_tokens = self.llm_client.count_tokens(prompt)
        
        print(f"初始 Prompt Token 数：{prompt_tokens} (阈值：{max_tokens})")
        
        # 如果超出阈值，开始动态缩减
        iteration = 0
        while prompt_tokens > max_tokens and iteration < 10:
            iteration += 1
            
            # 找出当前优先级最低的配置
            configs = [
                ('rag', rag_top_k, 3),  # (名称，当前值，最小值)
                ('sliding_window', sliding_window_chars, 500),
                ('hierarchy', hierarchy_levels, 1),
                ('entities', entity_max_count, 10),
            ]
            
            # 按优先级排序
            configs.sort(key=lambda x: PRIORITY[x[0]])
            
            # 缩减优先级最低的配置
            reduced = False
            for name, current_val, min_val in configs:
                if current_val > min_val:
                    ratio = REDUCE_RATIO[name]
                    new_val = int(current_val * ratio)
                    new_val = max(new_val, min_val)
                    
                    if name == 'rag':
                        rag_top_k = new_val
                        print(f"  缩减 RAG 数量：{rag_top_k}")
                    elif name == 'sliding_window':
                        sliding_window_chars = new_val
                        print(f"  缩减滑动窗口：{sliding_window_chars} 字符")
                    elif name == 'hierarchy':
                        hierarchy_levels = new_val
                        print(f"  缩减层级摘要：{hierarchy_levels} 层")
                    elif name == 'entities':
                        entity_max_count = new_val
                        print(f"  缩减实体数量：{entity_max_count}")
                    
                    reduced = True
                    break
            
            # 如果所有配置都已达到最小值，无法继续缩减
            if not reduced:
                print("警告：所有配置已达到最小值，无法继续缩减")
                break
            
            # 重新构建提示词
            prompt = build_prompt()
            prompt_tokens = self.llm_client.count_tokens(prompt)
            print(f"缩减后 Prompt Token 数：{prompt_tokens}")
        
        if prompt_tokens <= max_tokens:
            print(f"✓ Prompt Token 数符合要求：{prompt_tokens}/{max_tokens}")
        else:
            print(f"⚠ 警告：Prompt Token 数 ({prompt_tokens}) 仍超出阈值 ({max_tokens})")
        
        return prompt

    def _call_api(self, prompt: str, json_mode: bool = False) -> Optional[str]:
        """
        调用 LLM API 生成文本
        
        Args:
            prompt: 提示词
            json_mode: 是否强制 JSON 输出
            
        Returns:
            Optional[str]: 生成的文本，失败返回 None
        """
        # 使用 LLM 客户端生成
        if json_mode:
            result = self.llm_client.generate_json(prompt)
            return json.dumps(result, ensure_ascii=False) if result else None
        else:
            return self.llm_client.generate(prompt)

    def _extract_entities_from_text(self, text: str) -> List[str]:
        """
        从文本中提取实体（简化版，实际应用中可能需要更复杂的 NLP 处理）
        
        Args:
            text: 输入文本
            
        Returns:
            List[str]: 提取的实体列表
        """
        # 匹配可能的人名（简单的中文姓名模式）
        names = re.findall(r'[\u4e00-\u9fff]{2,4}(?:·[\u4e00-\u9fff]{2,4})*', text)
        # 去重并返回
        return list(set(names))

    def analyze_and_update_memory(self, chapter_num: int, chapter_title: str, chapter_content: str):
        """
        使用 LLM 分析章节内容，并将结果写入所有记忆模块

        Args:
            chapter_num: 章节号
            chapter_title: 章节标题
            chapter_content: 章节正文
        """
        analysis = self.chapter_analyzer.analyze(chapter_num, chapter_title, chapter_content)
        if analysis:
            apply_analysis_to_memory(
                analysis=analysis,
                chapter_num=chapter_num,
                chapter_title=chapter_title,
                chapter_content=chapter_content,
                entity_state=self.entity_state,
                character_relationship=self.character_relationship,
                long_term_memory=self.long_term_memory,
                hierarchical_summary=self.hierarchical_summary
            )
        else:
            # LLM 分析失败时，退化到简单的正则提取
            print("LLM 分析失败，使用简单提取作为后备方案")
            entities = self._extract_entities_from_text(chapter_content)
            self.long_term_memory.add_event(chapter_num, chapter_title, chapter_content, entities)
            simple_summary = self._simple_summarize(chapter_content)
            self.hierarchical_summary.add_low_level_summary(chapter_num, chapter_title, simple_summary)

    def _save_chapter(self, title: str, content: str):
        """
        保存章节到结果文件

        Args:
            title: 章节标题
            content: 章节内容
        """
        # 生成文件名
        chapter_files = [
            f for f in os.listdir(self.topic_dir)
            if f.startswith("chapter_") and f.endswith(".txt")
        ]
        next_num = len(chapter_files) + 1
        safe_title = title.replace('/', '_').replace(':', '_').replace('\\', '_')
        filename = os.path.join(
            self.topic_dir,
            f"chapter_{next_num:03d}_{safe_title}.txt"
        )

        # 验证输出路径安全（真实层级判断，避免同前缀兄弟目录绕过）
        if not self._is_within(Path(filename).resolve(), Path(self.topic_dir).resolve()):
            print(f"警告：检测到不安全的路径，已拒绝保存：{filename}")
            return

        with open(filename, 'w', encoding='utf-8') as f:
            f.write(f"# {title}\n\n")
            f.write(content)

        print(f"✓ 第 {next_num} 章已保存到文件")

        # 使用后台处理器异步处理后续任务
        # 这样主线程可以立即返回，不阻塞用户
        self.post_processor.process_chapter(next_num, title, content)

    def update_story_outline(self, outline: str):
        """
        更新故事大纲
        
        Args:
            outline: 故事大纲
        """
        self.hierarchical_summary.update_high_level_outline(outline)

    def add_story_arc(self, arc_title: str, arc_summary: str):
        """
        添加故事弧线
        
        Args:
            arc_title: 弧线标题
            arc_summary: 弧线摘要
        """
        self.hierarchical_summary.add_mid_level_arc(arc_title, arc_summary)

    def add_chapter_summary(self, chapter_num: int, title: str, summary: str):
        """
        添加章节摘要
        
        Args:
            chapter_num: 章节编号
            title: 章节标题
            summary: 章节摘要
        """
        self.hierarchical_summary.add_low_level_summary(chapter_num, title, summary)

    def add_event_to_memory(self, chapter_num: int, title: str, content: str):
        """
        添加事件到长期记忆
        
        Args:
            chapter_num: 章节编号
            title: 章节标题
            content: 章节内容
        """
        entities = self._extract_entities_from_text(content)
        self.long_term_memory.add_event(chapter_num, title, content, entities)

    def initialize_first_chapter(self, title: str, content: str):
        """
        初始化第一章内容

        Args:
            title: 章节标题
            content: 章节内容
        """
        # 添加到滑动窗口
        self.sliding_window.add_content(title, content)

        # 保存第一章
        self._save_chapter(title, content)

        # 使用 LLM 分析第一章并更新记忆系统
        self.analyze_and_update_memory(1, title, content)

    def _simple_summarize(self, text: str, max_length: int = 100) -> str:
        """
        简单的文本摘要（截断版）

        Args:
            text: 输入文本
            max_length: 最大长度

        Returns:
            str: 摘要文本
        """
        if len(text) <= max_length:
            return text

        # 找到合适的截断点（中文和英文句子边界）
        truncated = text[:max_length]
        last_sentence_end = max(
            truncated.rfind('。'),
            truncated.rfind('！'),
            truncated.rfind('？'),
            truncated.rfind('.'),
            truncated.rfind('!'),
            truncated.rfind('?'),
        )
        if last_sentence_end > max_length // 2:
            truncated = truncated[:last_sentence_end + 1]
        return truncated + "..."
