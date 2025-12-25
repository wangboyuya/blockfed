"""
数据块市场服务 - 处理数据块的初始化、购买、出售等业务逻辑
"""
import os
import pickle
import random
import json
from decimal import Decimal
from django.conf import settings
from django.db import transaction
from .models import DataBlock, UserDataBlock, DataBlockTransaction, User


class DataBlockInitService:
    """数据块初始化服务 - 从sampling文件加载数据块到数据库"""

    @staticmethod
    def initialize_datablocks(dataset_type='CIFAR10'):
        """
        初始化数据块到数据库

        Args:
            dataset_type: 数据集类型 (CIFAR10/MNIST)

        Returns:
            dict: 初始化结果
        """
        base_dir = settings.BASE_DIR
        core_dir = os.path.join(base_dir, 'federation_core')
        sampling_file = os.path.join(core_dir, f'sampling_results/sampling_{dataset_type.lower()}.pkl')

        if not os.path.exists(sampling_file):
            return {
                'success': False,
                'message': f'采样文件不存在: {sampling_file}'
            }

        try:
            # 读取数据块信息
            with open(sampling_file, 'rb') as f:
                data_blocks_data = pickle.load(f)
                blocks_dict = data_blocks_data.get('indices_per_participant', {})

            created_count = 0
            updated_count = 0

            # 批量创建数据块
            for block_id, indices in blocks_dict.items():
                data_size = len(indices) if isinstance(indices, list) else 0

                # 使用 update_or_create 避免重复
                block, created = DataBlock.objects.update_or_create(
                    block_id=block_id,
                    defaults={
                        'dataset_type': dataset_type,
                        'data_size': data_size,
                        'base_price': 10,
                        'is_available': True,
                        'current_owner': None
                    }
                )

                if created:
                    created_count += 1
                else:
                    updated_count += 1

            return {
                'success': True,
                'message': f'数据块初始化成功',
                'total_blocks': len(blocks_dict),
                'created': created_count,
                'updated': updated_count
            }

        except Exception as e:
            return {
                'success': False,
                'message': f'初始化失败: {str(e)}'
            }


class DataBlockMarketService:
    """数据块市场服务 - 处理购买、出售等交易"""

    # 定价配置
    PURCHASE_PRICE = 10  # 购买价格（虚拟币）
    SELL_PRICE = 8       # 出售价格（虚拟币，原价的80%）

    @staticmethod
    @transaction.atomic
    def allocate_free_blocks(user, num_blocks=3):
        """
        为新用户分配免费数据块

        Args:
            user: User对象
            num_blocks: 分配数量

        Returns:
            dict: 分配结果
        """
        try:
            # 获取可用的数据块（未被占用）
            available_blocks = DataBlock.objects.filter(
                current_owner=None,
                is_available=True
            ).order_by('?')[:num_blocks]  # 随机选择

            if len(available_blocks) < num_blocks:
                return {
                    'success': False,
                    'message': f'可用数据块不足，需要{num_blocks}个，当前仅有{len(available_blocks)}个'
                }

            allocated_blocks = []

            for block in available_blocks:
                # 分配给用户
                block.current_owner = user
                block.save()

                # 创建持有记录
                UserDataBlock.objects.create(
                    user=user,
                    data_block=block,
                    acquisition_type='free'
                )

                # 创建交易记录
                DataBlockTransaction.objects.create(
                    user=user,
                    data_block=block,
                    transaction_type='gift',
                    price=0,
                    coins_before=user.virtual_coins,
                    coins_after=user.virtual_coins,
                    description=f'注册赠送数据块 #{block.block_id}'
                )

                allocated_blocks.append(block.block_id)

            # 同步到 user_database.json
            DataBlockMarketService._sync_to_user_database(user)

            return {
                'success': True,
                'message': f'成功分配{len(allocated_blocks)}个数据块',
                'block_ids': allocated_blocks
            }

        except Exception as e:
            return {
                'success': False,
                'message': f'分配失败: {str(e)}'
            }

    @staticmethod
    @transaction.atomic
    def purchase_block(user, block_id):
        """
        购买数据块

        Args:
            user: User对象
            block_id: 数据块ID

        Returns:
            dict: 购买结果
        """
        try:
            # 检查数据块是否存在
            try:
                block = DataBlock.objects.get(block_id=block_id)
            except DataBlock.DoesNotExist:
                return {
                    'success': False,
                    'message': f'数据块 #{block_id} 不存在'
                }

            # 检查是否已被占用
            if block.current_owner is not None:
                return {
                    'success': False,
                    'message': f'数据块 #{block_id} 已被用户 {block.current_owner.username} 占用'
                }

            # 检查用户是否已拥有此数据块
            if UserDataBlock.objects.filter(user=user, data_block=block).exists():
                return {
                    'success': False,
                    'message': f'您已拥有数据块 #{block_id}'
                }

            # 检查虚拟币余额
            if user.virtual_coins < DataBlockMarketService.PURCHASE_PRICE:
                return {
                    'success': False,
                    'message': f'虚拟币不足，需要{DataBlockMarketService.PURCHASE_PRICE}币，当前仅有{user.virtual_coins}币'
                }

            # 扣除虚拟币
            coins_before = user.virtual_coins
            user.virtual_coins -= DataBlockMarketService.PURCHASE_PRICE
            user.save()

            # 分配数据块
            block.current_owner = user
            block.save()

            # 创建持有记录
            UserDataBlock.objects.create(
                user=user,
                data_block=block,
                acquisition_type='purchased'
            )

            # 创建交易记录
            DataBlockTransaction.objects.create(
                user=user,
                data_block=block,
                transaction_type='purchase',
                price=DataBlockMarketService.PURCHASE_PRICE,
                coins_before=coins_before,
                coins_after=user.virtual_coins,
                description=f'购买数据块 #{block_id}'
            )

            # 同步到 user_database.json
            DataBlockMarketService._sync_to_user_database(user)

            return {
                'success': True,
                'message': f'成功购买数据块 #{block_id}',
                'block_id': block_id,
                'price': DataBlockMarketService.PURCHASE_PRICE,
                'remaining_coins': user.virtual_coins
            }

        except Exception as e:
            return {
                'success': False,
                'message': f'购买失败: {str(e)}'
            }

    @staticmethod
    @transaction.atomic
    def sell_block(user, block_id):
        """
        出售数据块回系统

        Args:
            user: User对象
            block_id: 数据块ID

        Returns:
            dict: 出售结果
        """
        try:
            # 检查用户是否拥有此数据块
            try:
                user_block = UserDataBlock.objects.get(user=user, data_block__block_id=block_id)
                block = user_block.data_block
            except UserDataBlock.DoesNotExist:
                return {
                    'success': False,
                    'message': f'您不拥有数据块 #{block_id}'
                }

            # 增加虚拟币
            coins_before = user.virtual_coins
            user.virtual_coins += DataBlockMarketService.SELL_PRICE
            user.save()

            # 释放数据块
            block.current_owner = None
            block.save()

            # 删除持有记录
            user_block.delete()

            # 创建交易记录
            DataBlockTransaction.objects.create(
                user=user,
                data_block=block,
                transaction_type='sell',
                price=DataBlockMarketService.SELL_PRICE,
                coins_before=coins_before,
                coins_after=user.virtual_coins,
                description=f'出售数据块 #{block_id} 回系统'
            )

            # 同步到 user_database.json
            DataBlockMarketService._sync_to_user_database(user)

            return {
                'success': True,
                'message': f'成功出售数据块 #{block_id}',
                'block_id': block_id,
                'price': DataBlockMarketService.SELL_PRICE,
                'remaining_coins': user.virtual_coins
            }

        except Exception as e:
            return {
                'success': False,
                'message': f'出售失败: {str(e)}'
            }

    @staticmethod
    def get_available_blocks(dataset_type='CIFAR10', limit=100):
        """
        获取可购买的数据块列表

        Args:
            dataset_type: 数据集类型
            limit: 返回数量限制

        Returns:
            list: 可购买的数据块列表
        """
        blocks = DataBlock.objects.filter(
            dataset_type=dataset_type,
            current_owner=None,
            is_available=True
        ).order_by('block_id')[:limit]

        return [{
            'block_id': block.block_id,
            'dataset_type': block.dataset_type,
            'data_size': block.data_size,
            'price': block.base_price,
            'is_available': True
        } for block in blocks]

    @staticmethod
    def get_user_blocks(user):
        """
        获取用户拥有的数据块

        Args:
            user: User对象

        Returns:
            list: 用户的数据块列表
        """
        user_blocks = UserDataBlock.objects.filter(user=user).select_related('data_block')

        return [{
            'block_id': ub.data_block.block_id,
            'dataset_type': ub.data_block.dataset_type,
            'data_size': ub.data_block.data_size,
            'acquisition_type': ub.acquisition_type,
            'acquisition_type_display': ub.get_acquisition_type_display(),
            'acquired_at': ub.acquired_at.isoformat()
        } for ub in user_blocks]

    @staticmethod
    def get_market_stats():
        """
        获取数据块市场统计信息

        Returns:
            dict: 市场统计数据
        """
        total_blocks = DataBlock.objects.count()
        available_blocks = DataBlock.objects.filter(current_owner=None).count()
        occupied_blocks = total_blocks - available_blocks

        return {
            'total_blocks': total_blocks,
            'available_blocks': available_blocks,
            'occupied_blocks': occupied_blocks,
            'occupation_rate': (occupied_blocks / total_blocks * 100) if total_blocks > 0 else 0,
            'purchase_price': DataBlockMarketService.PURCHASE_PRICE,
            'sell_price': DataBlockMarketService.SELL_PRICE
        }

    @staticmethod
    def _sync_to_user_database(user):
        """
        将用户的数据块同步到 user_database.json

        Args:
            user: User对象
        """
        try:
            base_dir = settings.BASE_DIR
            core_dir = os.path.join(base_dir, 'federation_core')
            user_db_path = os.path.join(core_dir, 'user_database.json')

            # 加载现有数据
            if os.path.exists(user_db_path):
                with open(user_db_path, 'r') as f:
                    user_db = json.load(f)
            else:
                user_db = {"user_info": {}}

            # 获取用户的数据块
            user_blocks = UserDataBlock.objects.filter(user=user).values_list('data_block__block_id', flat=True)
            block_ids = list(user_blocks)

            # 更新用户信息
            user_db['user_info'][str(user.id)] = {
                "user_id": user.id,
                "user_name": user.username,
                "virtual_coins": user.virtual_coins,
                "assigned_data_indices": block_ids,
                "data_block_count": len(block_ids)
            }

            # 保存到文件
            os.makedirs(os.path.dirname(user_db_path), exist_ok=True)
            with open(user_db_path, 'w') as f:
                json.dump(user_db, f, indent=2)

        except Exception as e:
            # 同步失败不影响主流程，只记录日志
            print(f"同步到 user_database.json 失败: {e}")


# 全局服务实例
datablock_init_service = DataBlockInitService()
datablock_market_service = DataBlockMarketService()
