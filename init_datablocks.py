#!/usr/bin/env python
"""
初始化数据块到数据库
"""
import os
import django

# 设置Django环境
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'federation_platform.settings')
django.setup()

from federation_app.datablock_service import DataBlockInitService

if __name__ == "__main__":
    print("🚀 开始初始化数据块...")

    # 初始化CIFAR10数据块
    result = DataBlockInitService.initialize_datablocks(dataset_type='CIFAR10')

    if result['success']:
        print(f"✅ {result['message']}")
        print(f"   总数据块: {result['total_blocks']}")
        print(f"   新创建: {result['created']}")
        print(f"   已更新: {result['updated']}")
    else:
        print(f"❌ {result['message']}")
