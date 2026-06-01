#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
无限小说生成系统 - 主菜单
提供创建新小说和续写已有小说的选项
"""

import os
import sys


def main():
    print("欢迎使用无限小说生成系统！")
    print("="*50)
    print("请选择操作:")
    print("1. 创建新小说")
    print("2. 续写已有小说")
    
    while True:
        choice = input("\n请输入选择 (1/2): ").strip()
        if choice == '1':
            # 导入并运行创建新小说的函数
            try:
                from create_novel import create_new_novel
                create_new_novel()
            except ImportError:
                print("错误: 未找到 create_novel.py 文件")
            break
        elif choice == '2':
            # 导入并运行续写小说的函数
            try:
                from continue_novel import continue_novel_interactive
                continue_novel_interactive()
            except ImportError:
                print("错误: 未找到 continue_novel.py 文件")
            break
        else:
            print("请输入有效选择 (1/2)")


if __name__ == "__main__":
    main()