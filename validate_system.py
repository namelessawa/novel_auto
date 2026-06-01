#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
系统功能验证脚本
"""

import os
from core import NovelGenerator

def test_system_structure():
    print("无限小说生成系统结构验证")
    print("="*50)

    # 检查必要的文件是否存在
    required_files = [
        'main.py',
        'create_novel.py',
        'continue_novel.py',
        'core/generator.py',
        'core/config.py',
        'memory_system/sliding_window.py',
        'memory_system/entity_state.py',
        'memory_system/hierarchical_summary.py',
        'memory_system/long_term_memory.py',
        'memory_system/character_relationship.py'
    ]
    
    all_present = True
    for file in required_files:
        if os.path.exists(file):
            print(f"✓ {file}")
        else:
            print(f"✗ {file} - 缺失")
            all_present = False
    
    if not all_present:
        print("\n⚠️  系统文件不完整")
        return False
    
    print("\n✓ 所有系统文件存在")
    
    # 测试模块导入
    try:
        from create_novel import create_new_novel
        print("✓ create_novel 模块可导入")
    except ImportError as e:
        print(f"✗ create_novel 模块导入失败: {e}")
        all_present = False
    
    try:
        from continue_novel import continue_novel_interactive
        print("✓ continue_novel 模块可导入")
    except ImportError as e:
        print(f"✗ continue_novel 模块导入失败: {e}")
        all_present = False
    
    # 测试API配置
    try:
        from core.config import DEEPSEEK_API_KEY
        if DEEPSEEK_API_KEY:
            print("✓ API密钥已配置")
        else:
            print("? API密钥未配置（需要用户设置）")
    except ImportError as e:
        print(f"✗ API配置导入失败: {e}")
        all_present = False
    
    if all_present:
        print("\n✓ 系统结构验证通过！")
        print("\n要开始使用系统，请运行: python main.py")
        return True
    else:
        print("\n✗ 系统结构验证失败！")
        return False

if __name__ == "__main__":
    test_system_structure()