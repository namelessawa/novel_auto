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
    
    # 测试 LLM 提供商配置（仅展示非敏感元数据）
    try:
        from core.config import _safe_summary, get_active_llm_config
        _summary = _safe_summary(get_active_llm_config())
        _label = _summary["label"]
        _provider_id = _summary["provider"]
        _endpoint = _summary["endpoint"]
        _model_name = _summary["model"]
        print(f"  当前 LLM 提供商: {_label} ({_provider_id})")
        print(f"  endpoint: {_endpoint}")
        print(f"  model:    {_model_name}")
        if _summary["credential_status"] == "configured":
            print("✓ 凭据已配置")
        else:
            print("? 凭据未配置（请在 .env 或前端设置中填入）")
    except ImportError as e:
        print(f"✗ 配置导入失败: {e}")
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