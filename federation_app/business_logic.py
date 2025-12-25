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

        return created_holdings

    @staticmethod
    @transaction.atomic
    def distribute_rewards_by_contribution(task, contribution_data):
        """
        根据Shapley值贡献度分配奖金（奖金池模式）

        Args:
            task: FederationTask实例
            contribution_data: {user_id: contribution_value} 字典
        """
        if task.payment_mode != 'reward':
            raise ValueError(f"任务{task.task_id}不是奖金池模式，无法分配奖金")

        if task.reward_pool <= 0:
            raise ValueError("奖金池为0，无法分配奖金")

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

            contribution_ratio = Decimal(str(contribution)) / Decimal(str(total_contribution))
            reward_amount = task.reward_pool * contribution_ratio

            balance_before = user.balance
            user.balance += reward_amount
            user.save()

            Transaction.objects.create(
                user=user,
                transaction_type='reward_distribution',
                amount=reward_amount,
                balance_before=balance_before,
                balance_after=user.balance,
                description=f'任务{task.task_name}奖金分配',
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
                'reward_amount': float(reward_amount)
            })

            total_distributed += reward_amount

        task.model_status = 'offline'
        task.save()

        return distributions


class ModelUsageService:
    """模型使用和收益分配服务"""

    @staticmethod
    @transaction.atomic
    def charge_and_distribute(task, user, prediction_result='', input_hash=''):
        """
        模型使用付费并自动分配收益给股东

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

        usage_fee = task.usage_fee_per_request

        if user.balance < usage_fee:
            raise ValueError(f"余额不足，需要¥{usage_fee}，当前余额¥{user.balance}")

        balance_before = user.balance
        user.balance -= usage_fee
        user.save()

        Transaction.objects.create(
            user=user,
            transaction_type='model_usage',
            amount=usage_fee,
            balance_before=balance_before,
            balance_after=user.balance,
            description=f'使用模型{task.task_name}进行预测',
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

        if task.payment_mode == 'shareholding':
            shareholdings = ModelShareholding.objects.filter(task=task)

            for holding in shareholdings:
                revenue_amount = usage_fee * holding.share_ratio

                shareholder_balance_before = holding.user.balance
                holding.user.balance += revenue_amount
                holding.user.save()

                Transaction.objects.create(
                    user=holding.user,
                    transaction_type='revenue',
                    amount=revenue_amount,
                    balance_before=shareholder_balance_before,
                    balance_after=holding.user.balance,
                    description=f'模型{task.task_name}使用收益分红',
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
                    'revenue_amount': float(revenue_amount)
                })

        return {
            'usage_record_id': usage_record.id,
            'usage_fee': float(usage_fee),
            'user_balance_after': float(user.balance),
            'distributions': distributions
        }

    @staticmethod
    def check_model_available(task):
        """检查模型是否可用"""
        return task.model_status == 'online' and task.status == 'completed'
