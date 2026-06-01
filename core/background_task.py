"""
后台任务管理器
使用 threading 实现异步处理，避免阻塞主线程
"""

import threading
import queue
import time
from typing import Callable, Any, Optional


class BackgroundTaskManager:
    """
    后台任务管理器
    管理异步任务队列，按顺序执行耗时操作
    """
    
    def __init__(self, max_workers: int = 2):
        """
        初始化后台任务管理器
        
        Args:
            max_workers: 最大工作线程数
        """
        self.task_queue = queue.Queue()
        self.workers = []
        self.max_workers = max_workers
        self.running = False
        self._stats_lock = threading.Lock()
        self.stats = {
            'completed': 0,
            'failed': 0,
            'pending': 0
        }
    
    def start(self):
        """启动后台工作线程"""
        if self.running:
            return
        
        self.running = True
        for i in range(self.max_workers):
            worker = threading.Thread(target=self._worker_loop, daemon=True)
            worker.start()
            self.workers.append(worker)
        
        print(f"后台任务管理器已启动 ({self.max_workers} 工作线程)")
    
    def stop(self):
        """停止后台任务管理器"""
        self.running = False
        # 发送哨兵值唤醒所有工作线程
        for _ in self.workers:
            self.task_queue.put(None)
        for worker in self.workers:
            worker.join(timeout=5.0)
        self.workers.clear()
        print("后台任务管理器已停止")
    
    def _worker_loop(self):
        """工作线程循环"""
        while self.running:
            try:
                # 从队列获取任务（超时 1 秒）
                task = self.task_queue.get(timeout=1.0)
                if task is None:
                    break
                
                func, args, kwargs, callback = task
                
                try:
                    # 执行任务
                    result = func(*args, **kwargs)
                    with self._stats_lock:
                        self.stats['completed'] += 1

                    # 调用回调函数
                    if callback:
                        callback(True, result)

                except Exception as e:
                    with self._stats_lock:
                        self.stats['failed'] += 1
                    print(f"后台任务执行失败：{e}")

                    if callback:
                        callback(False, str(e))

                finally:
                    self.task_queue.task_done()
                    with self._stats_lock:
                        self.stats['pending'] = self.task_queue.qsize()
                    
            except queue.Empty:
                continue
    
    def submit(self, func: Callable, *args, callback: Optional[Callable] = None, **kwargs):
        """
        提交任务到后台队列
        
        Args:
            func: 要执行的函数
            *args: 函数参数
            callback: 回调函数 callback(success, result)
            **kwargs: 函数关键字参数
        """
        self.stats['pending'] = self.task_queue.qsize() + 1
        self.task_queue.put((func, args, kwargs, callback))
    
    def wait_completion(self, timeout: float = None):
        """
        等待所有任务完成

        Args:
            timeout: 超时时间（秒）
        """
        if timeout is not None:
            import time
            deadline = time.monotonic() + timeout
            while not self.task_queue.empty() and time.monotonic() < deadline:
                time.sleep(0.1)
        else:
            self.task_queue.join()
    
    def get_stats(self) -> dict:
        """获取任务统计信息"""
        with self._stats_lock:
            return self.stats.copy()


# 全局后台任务管理器实例
_background_manager = None
_manager_lock = threading.Lock()


def get_background_manager() -> BackgroundTaskManager:
    """获取全局后台任务管理器实例（单例）"""
    global _background_manager
    
    with _manager_lock:
        if _background_manager is None:
            _background_manager = BackgroundTaskManager(max_workers=2)
            _background_manager.start()
        
        return _background_manager


# 装饰器：将函数转换为后台任务
def run_in_background(func: Callable) -> Callable:
    """
    装饰器：将函数转换为后台异步任务
    
    用法:
        @run_in_background
        def my_slow_function(data):
            # 耗时操作
            return result
        
        # 调用时立即返回，不阻塞
        my_slow_function(data)
    """
    def wrapper(*args, callback: Optional[Callable] = None, **kwargs):
        manager = get_background_manager()
        manager.submit(func, *args, callback=callback, **kwargs)
    return wrapper


# 示例：后台处理章节多媒体和记忆更新
class ChapterPostProcessor:
    """
    章节后处理器
    在章节生成后异步处理以下任务：
    1. 更新记忆系统
    2. 生成多媒体内容
    3. 更新向量索引
    """
    
    def __init__(self, generator):
        """
        初始化后处理器
        
        Args:
            generator: NovelGenerator 实例
        """
        self.generator = generator
        self.manager = get_background_manager()
    
    def process_chapter(self, chapter_num: int, title: str, content: str):
        """
        异步处理章节
        
        Args:
            chapter_num: 章节号
            title: 章节标题
            content: 章节内容
        """
        # 提交到后台任务队列
        self.manager.submit(
            self._process_chapter_sync,
            chapter_num, title, content,
            callback=self._on_process_complete
        )
        print(f"已提交章节 {chapter_num} 的后台处理任务")
    
    def _process_chapter_sync(self, chapter_num: int, title: str, content: str):
        """
        同步处理章节（在后台线程中执行）
        
        Args:
            chapter_num: 章节号
            title: 章节标题
            content: 章节内容
            
        Returns:
            dict: 处理结果
        """
        result = {
            'chapter_num': chapter_num,
            'title': title,
            'tasks': {}
        }

        # 注意：实体状态与长期记忆的更新由主线程的
        # NovelGenerator.analyze_and_update_memory（基于 LLM 分析）统一负责。
        # 此后台处理器不再重复进行正则实体提取 / add_event，
        # 以避免：
        #   1) 同一章节被写入记忆两次（重复事件）；
        #   2) 后台线程与主线程并发改写 entity_state / long_term_memory 造成数据竞争。
        result['tasks']['entities'] = 'skipped (owned by main thread analyze_and_update_memory)'
        result['tasks']['memory'] = 'skipped (owned by main thread analyze_and_update_memory)'

        # 生成多媒体内容（如果启用）——这是真正适合放到后台的独立耗时任务
        if self.generator.enable_multimedia and self.generator.multimedia_manager:
            try:
                print(f"  [{chapter_num}] 正在生成多媒体内容...")
                self.generator.multimedia_manager.generate_multimedia_for_chapter(
                    chapter_title=title,
                    chapter_content=content,
                    topic_dir=self.generator.topic_dir
                )
                result['tasks']['multimedia'] = 'success'
            except Exception as e:
                print(f"  [{chapter_num}] 多媒体生成失败：{e}")
                result['tasks']['multimedia'] = f'failed: {e}'
        else:
            result['tasks']['multimedia'] = 'disabled'
        
        # 4. 滑动窗口已在主线程中更新，此处跳过避免重复
        result['tasks']['sliding_window'] = 'skipped (updated in main thread)'
        
        return result
    
    def _on_process_complete(self, success: bool, result: Any):
        """
        处理完成的回调
        
        Args:
            success: 是否成功
            result: 处理结果
        """
        if success:
            stats = self.manager.get_stats()
            print(f"✓ 章节处理完成 | 已完成：{stats['completed']} | 失败：{stats['failed']} | 待处理：{stats['pending']}")
        else:
            print(f"✗ 章节处理失败：{result}")


# 使用示例
if __name__ == "__main__":
    # 启动后台管理器
    manager = get_background_manager()
    
    # 定义耗时任务
    def slow_task(name, duration):
        print(f"开始任务：{name}")
        time.sleep(duration)
        print(f"完成任务：{name}")
        return f"{name} 的结果"
    
    # 提交任务（不阻塞）
    def on_complete(success, result):
        if success:
            print(f"回调：{result}")
        else:
            print(f"失败：{result}")
    
    print("提交任务 1...")
    manager.submit(slow_task, "任务 1", 3, callback=on_complete)
    
    print("提交任务 2...")
    manager.submit(slow_task, "任务 2", 2, callback=on_complete)
    
    print("提交任务 3...")
    manager.submit(slow_task, "任务 3", 1, callback=on_complete)
    
    # 等待所有任务完成
    print("等待任务完成...")
    manager.wait_completion()
    
    print(f"最终统计：{manager.get_stats()}")
