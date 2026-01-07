#!/usr/bin/env python
"""
重新绑定所有用户到固定助记词的Ganache账户
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'federation_platform.settings')
django.setup()

from federation_app.models import User
from federation_app.blockchain_utils import w3

print("🔄 重新绑定用户到固定助记词的Ganache账户\n")

users = User.objects.all().order_by('id')

for i, user in enumerate(users[:10]):
    user.ganache_index = i
    # 重置虚拟币为0（因为新的区块链）
    user.virtual_coins = 0
    user.save()

    print(f"✅ {user.username}")
    print(f"   Ganache索引: {user.ganache_index}")
    print(f"   钱包地址: {user.wallet_address}")
    print(f"   ETH余额: {user.eth_balance} ETH")
    print(f"   虚拟币: {user.virtual_coins}\n")

print("🎉 绑定完成！现在地址是固定的，重启Ganache也不会变化。")
