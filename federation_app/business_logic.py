"""
核心业务逻辑：股份分配、收益分配、奖金分配
"""
from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from .models import (
    FederationTask, ModelShareholding, RewardDistribution,
    ModelUsageRecord, RevenueDistribution, Transaction, User
)
from .blockchain_utils import sync_contribution_to_chain,get_contract,w3
from decimal import Decimal

class ShareManagementService:
    """股份管理服务"""

    @staticmethod
    @transaction.atomic
    def distribute_shares_by_contribution(task, contribution_data):
        """
        根据Shapley值贡献度分配股份（股份制模式）

        Args:
            task: FederationTask实例
            contribution_data: {user_id: contribution_value} 字典
        """
        if task.payment_mode != 'shareholding':
            raise ValueError(f"任务{task.task_id}不是股份制模式，无法分配股份")

        total_contribution = sum(contribution_data.values())
        if total_contribution == 0:
            raise ValueError("总贡献度为0，无法分配股份")

        created_holdings = []

        for user_id, contribution in contribution_data.items():
            try:
                user = User.objects.get(id=user_id)
            except User.DoesNotExist:
                continue

            share_ratio = Decimal(str(contribution)) / Decimal(str(total_contribution))

            holding, created = ModelShareholding.objects.update_or_create(
                task=task,
                user=user,
                defaults={
                    'share_ratio': share_ratio,
                    'initial_contribution': Decimal(str(contribution)),
                    'tradable': True
                }
            )
            created_holdings.append({
                'user_id': user.id,
                'username': user.username,
                'share_ratio': float(share_ratio),
                'share_percentage': float(share_ratio * 100),
                'contribution': float(contribution)
            })

        task.model_status = 'online'
        task.save()
        # --- 新增区块链同步逻辑 ---
        # model_hash 可以取模型文件的 MD5 或固定占位符
        model_hash = "hash_" + task.task_id 
        success = sync_contribution_to_chain(task.task_id, contribution_data, model_hash)
        
        if success:
            print(f"任务 {task.task_id} 贡献度已成功上链存证")
        # ------------------------

        # 2. [新增逻辑] 同步到区块链
        try:
            manager_contract = get_contract('FederationManager')
            admin_account = w3.eth.accounts[0]  # 使用 Ganache 第一个账号作为管理员
            
            # 转换数据格式
            user_addresses = []
            ratios = []
            for user_id, contribution in contribution_data.items():
                # 暂时模拟地址：每个用户 ID 对应 Ganache 的一个账号
                # 生产环境下你需要在 User 模型里加一个 wallet_address 字段
                simulated_address = w3.eth.accounts[int(user_id) % 10]
                user_addresses.append(simulated_address)
                # Solidity 不支持浮点数，比例放大 10000 倍（例如 0.4567 -> 4567）
                ratios.append(int(float(contribution) * 10000))

            # 调用合约的 setContributionRatios 方法
            # model_hash 可以取模型文件的路径哈希
            model_hash = f"hash_{task.task_id}_{task.current_epoch}"
            
            tx_hash = manager_contract.functions.setContributionRatios(
                task.task_id, 
                user_addresses, 
                ratios, 
                model_hash
            ).transact({'from': admin_account})
            
            # 等待交易确认
            receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
            print(f"区块链同步成功！交易哈希: {receipt.transactionHash.hex()}")
            
        except Exception as e:
            print(f"区块链同步失败: {str(e)}")

        return created_holdings

    @staticmethod
    @transaction.atomic
    def distribute_rewards_by_contribution(task, contribution_data):
        """
        根据Shapley值贡献度分配奖金（奖金池模式）- 使用ETH转账

        Args:
            task: FederationTask实例
            contribution_data: {user_id: contribution_value} 字典
        """
        if task.payment_mode != 'reward':
            raise ValueError(f"任务{task.task_id}不是奖金池模式，无法分配奖金")

        if task.reward_pool <= 0:
            raise ValueError("奖金池为0，无法分配奖金")

        if not task.creator or not task.creator.wallet_address:
            raise ValueError("任务创建者未绑定Ganache账户，无法转账")

        total_contribution = sum(contribution_data.values())
        if total_contribution == 0:
            raise ValueError("总贡献度为0，无法分配奖金")

        distributions = []
        total_distributed = Decimal('0.00')

        for user_id, contribution in contribution_data.items():
            try:
                user = User.objects.get(id=user_id)
            except User.DoesNotExist:
                continue

            if not user.wallet_address:
                print(f"警告: 用户{user.username}(ID:{user_id})未绑定Ganache账户，跳过奖金分配")
                continue

            contribution_ratio = Decimal(str(contribution)) / Decimal(str(total_contribution))
            reward_amount = task.reward_pool * contribution_ratio

            # 获取转账前余额
            balance_before = user.eth_balance

            # 从任务创建者账户转ETH到参与者账户
            try:
                amount_wei = w3.to_wei(reward_amount, 'ether')
                tx_hash = w3.eth.send_transaction({
                    'from': task.creator.wallet_address,
                    'to': user.wallet_address,
                    'value': amount_wei,
                    'gas': 21000
                })
                receipt = w3.eth.wait_for_transaction_receipt(tx_hash)

                if receipt.status != 1:
                    print(f"警告: 转账给{user.username}失败，跳过")
                    continue

                balance_after = user.eth_balance

                # 记录交易
                Transaction.objects.create(
                    user=user,
                    transaction_type='reward_distribution',
                    amount=reward_amount,
                    balance_before=Decimal(str(balance_before)),
                    balance_after=Decimal(str(balance_after)),
                    description=f'任务{task.task_name}奖金分配 ({float(contribution_ratio*100):.2f}%贡献度)',
                    related_task=task
                )

                distribution = RewardDistribution.objects.create(
                    task=task,
                    user=user,
                    contribution_ratio=contribution_ratio,
                    reward_amount=reward_amount,
                    paid=True
                )

                distributions.append({
                    'user_id': user.id,
                    'username': user.username,
                    'contribution_ratio': float(contribution_ratio),
                    'reward_amount': float(reward_amount),
                    'tx_hash': receipt.transactionHash.hex()
                })

                total_distributed += reward_amount

            except Exception as e:
                print(f"转账给用户{user.username}失败: {e}")
                continue

        # 奖金分配完成后，模型也应该上线（可用于预测）
        task.model_status = 'online'
        task.save()

        return distributions


class ModelUsageService:
    """模型使用和收益分配服务"""

    @staticmethod
    @transaction.atomic
    def charge_and_distribute(task, user, prediction_result='', input_hash=''):
        """
        模型使用付费并自动分配收益给股东 - 使用ETH转账

        Args:
            task: FederationTask实例
            user: 使用者User实例
            prediction_result: 预测结果
            input_hash: 输入数据哈希

        Returns:
            dict: 使用记录和分配详情
        """
        if task.model_status != 'online':
            raise ValueError(f"模型{task.task_name}未上线，无法使用")

        if not user.wallet_address:
            raise ValueError(f"用户未绑定Ganache账户，无法使用模型")

        usage_fee = task.usage_fee_per_request

        if user.eth_balance < float(usage_fee):
            raise ValueError(f"ETH余额不足，需要{usage_fee} ETH，当前余额{user.eth_balance:.4f} ETH")

        balance_before = user.eth_balance

        # 将使用费转到任务创建者或收益池账户
        # 简化处理：直接转给任务创建者
        if not task.creator or not task.creator.wallet_address:
            raise ValueError("任务创建者未绑定Ganache账户，无法收款")

        # 执行ETH转账（用户->创建者）
        amount_wei = w3.to_wei(usage_fee, 'ether')
        tx_hash = w3.eth.send_transaction({
            'from': user.wallet_address,
            'to': task.creator.wallet_address,
            'value': amount_wei,
            'gas': 21000
        })

        receipt = w3.eth.wait_for_transaction_receipt(tx_hash)

        if receipt.status != 1:
            raise ValueError("区块链交易失败")

        balance_after = user.eth_balance

        Transaction.objects.create(
            user=user,
            transaction_type='model_usage',
            amount=usage_fee,
            balance_before=Decimal(str(balance_before)),
            balance_after=Decimal(str(balance_after)),
            description=f'使用模型{task.task_name}进行预测，交易哈希: {receipt.transactionHash.hex()[:10]}...',
            related_task=task
        )

        usage_record = ModelUsageRecord.objects.create(
            task=task,
            user=user,
            usage_fee=usage_fee,
            usage_type='prediction',
            input_data_hash=input_hash,
            prediction_result=prediction_result
        )

        task.total_revenue += usage_fee
        task.total_usage_count += 1
        task.save()

        distributions = []

        # 如果是股份制模式，分配收益给股东
        if task.payment_mode == 'shareholding':
            shareholdings = ModelShareholding.objects.filter(task=task)

            for holding in shareholdings:
                revenue_amount = usage_fee * holding.share_ratio

                if not holding.user.wallet_address:
                    print(f"警告: 股东{holding.user.username}未绑定Ganache账户，跳过分红")
                    continue

                shareholder_balance_before = holding.user.eth_balance

                # 从创建者账户转账给股东
                try:
                    revenue_wei = w3.to_wei(revenue_amount, 'ether')
                    dist_tx_hash = w3.eth.send_transaction({
                        'from': task.creator.wallet_address,
                        'to': holding.user.wallet_address,
                        'value': revenue_wei,
                        'gas': 21000
                    })

                    dist_receipt = w3.eth.wait_for_transaction_receipt(dist_tx_hash)

                    if dist_receipt.status != 1:
                        print(f"警告: 分红给{holding.user.username}失败")
                        continue

                    shareholder_balance_after = holding.user.eth_balance

                    Transaction.objects.create(
                        user=holding.user,
                        transaction_type='revenue',
                        amount=revenue_amount,
                        balance_before=Decimal(str(shareholder_balance_before)),
                        balance_after=Decimal(str(shareholder_balance_after)),
                        description=f'模型{task.task_name}使用收益分红 ({float(holding.share_ratio*100):.2f}%)',
                        related_task=task
                    )

                    RevenueDistribution.objects.create(
                        task=task,
                        shareholder=holding.user,
                        revenue_amount=revenue_amount,
                        source_usage=usage_record,
                        share_ratio_snapshot=holding.share_ratio
                    )

                    distributions.append({
                        'shareholder_id': holding.user.id,
                        'shareholder_name': holding.user.username,
                        'share_ratio': float(holding.share_ratio),
                        'revenue_amount': float(revenue_amount),
                        'tx_hash': dist_receipt.transactionHash.hex()
                    })

                except Exception as e:
                    print(f"分红给股东{holding.user.username}失败: {e}")
                    continue

        return {
            'usage_record_id': usage_record.id,
            'usage_fee': float(usage_fee),
            'user_balance_after': user.eth_balance,
            'tx_hash': receipt.transactionHash.hex(),
            'distributions': distributions
        }

    @staticmethod
    def check_model_available(task):
        """检查模型是否可用"""
        return task.model_status == 'online' and task.status == 'completed'
