"""
用户资产管理相关视图
"""
import json
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.db.models import Sum
from .models import (
    User, ModelShareholding, TaskParticipant, FederationTask,
    RevenueDistribution, UserAsset, RewardDistribution
)


@require_http_methods(["GET"])
@login_required
def get_user_assets(request):
    """获取用户资产概览"""
    try:
        from .models import UserDataBlock
        user = request.user

        shareholdings = ModelShareholding.objects.filter(user=user)
        total_share_value = sum(
            float(sh.share_ratio) * float(sh.task.total_revenue)
            for sh in shareholdings
        )

        data_assets = UserAsset.objects.filter(user=user, asset_type='data')
        total_data_blocks = sum(float(asset.quantity) for asset in data_assets)

        # 获取用户数据块数量（新增）
        user_data_blocks_count = UserDataBlock.objects.filter(user=user).count()

        active_participations = TaskParticipant.objects.filter(
            user=user,
            is_active=True
        ).count()

        total_revenue = RevenueDistribution.objects.filter(
            shareholder=user
        ).aggregate(total=Sum('revenue_amount'))['total'] or 0

        total_rewards = RewardDistribution.objects.filter(
            user=user,
            paid=True
        ).aggregate(total=Sum('reward_amount'))['total'] or 0

        return JsonResponse({
            'success': True,
            'assets': {
                'eth_balance': user.eth_balance,  # 从Ganache读取ETH余额
                'ganache_index': user.ganache_index,  # Ganache账户索引
                'wallet_address': user.wallet_address,  # 钱包地址
                'virtual_coins': user.virtual_coins,  # 虚拟币（用于数据块交易）
                'model_shares_count': shareholdings.count(),
                'model_shares_value': total_share_value,
                'data_blocks_count': user_data_blocks_count,  # 新增
                'active_tasks_count': active_participations,
                'total_revenue': float(total_revenue),
                'total_rewards': float(total_rewards)
            }
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@require_http_methods(["GET"])
@login_required
def get_user_shareholdings(request):
    """获取用户持有的模型股份"""
    try:
        user = request.user
        shareholdings = ModelShareholding.objects.filter(user=user).select_related('task')

        shareholdings_data = [{
            'id': sh.id,
            'task_id': sh.task.task_id,
            'task_name': sh.task.task_name,
            'share_ratio': float(sh.share_ratio),
            'share_percentage': float(sh.share_ratio * 100),
            'initial_contribution': float(sh.initial_contribution),
            'tradable': sh.tradable,
            'task_revenue': float(sh.task.total_revenue),
            'task_status': sh.task.status,
            'model_status': sh.task.model_status,
            'acquired_at': sh.acquired_at.strftime('%Y-%m-%d %H:%M:%S')
        } for sh in shareholdings]

        return JsonResponse({
            'success': True,
            'shareholdings': shareholdings_data
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@require_http_methods(["GET"])
@login_required
def get_user_participations(request):
    """获取用户参与的任务"""
    try:
        user = request.user
        participations = TaskParticipant.objects.filter(user=user).select_related('task')

        participations_data = [{
            'id': p.id,
            'task_id': p.task.task_id,
            'task_name': p.task.task_name,
            'is_active': p.is_active,
            'joined_at': p.joined_at.strftime('%Y-%m-%d %H:%M:%S'),
            'task_status': p.task.status,
            'current_epoch': p.task.current_epoch,
            'total_epochs': p.task.total_epochs,
            'payment_mode': p.task.payment_mode,
            'payment_mode_display': p.task.get_payment_mode_display(),
            'dataset': p.task.dataset,  # 添加数据集
            'model_architecture': p.task.model_architecture  # 添加模型架构
        } for p in participations]

        return JsonResponse({
            'success': True,
            'participations': participations_data
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@require_http_methods(["GET"])
@login_required
def get_user_revenues(request):
    """获取用户收益记录"""
    try:
        user = request.user

        revenues = RevenueDistribution.objects.filter(
            shareholder=user
        ).select_related('task', 'source_usage').order_by('-distributed_at')[:50]

        revenues_data = [{
            'id': r.id,
            'task_id': r.task.task_id,
            'task_name': r.task.task_name,
            'revenue_amount': float(r.revenue_amount),
            'share_ratio': float(r.share_ratio_snapshot * 100),
            'distributed_at': r.distributed_at.strftime('%Y-%m-%d %H:%M:%S'),
            'source_usage_fee': float(r.source_usage.usage_fee)
        } for r in revenues]

        rewards = RewardDistribution.objects.filter(
            user=user
        ).select_related('task').order_by('-distributed_at')

        rewards_data = [{
            'id': r.id,
            'task_id': r.task.task_id,
            'task_name': r.task.task_name,
            'reward_amount': float(r.reward_amount),
            'contribution_ratio': float(r.contribution_ratio * 100),
            'paid': r.paid,
            'distributed_at': r.distributed_at.strftime('%Y-%m-%d %H:%M:%S')
        } for r in rewards]

        return JsonResponse({
            'success': True,
            'revenues': revenues_data,
            'rewards': rewards_data
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@require_http_methods(["GET"])
@login_required
def get_user_data_blocks(request):
    """获取用户持有的数据块"""
    try:
        user = request.user
        data_assets = UserAsset.objects.filter(user=user, asset_type='data')

        data_blocks = [{
            'id': asset.id,
            'asset_reference': asset.asset_reference,
            'quantity': float(asset.quantity),
            'created_at': asset.created_at.strftime('%Y-%m-%d %H:%M:%S')
        } for asset in data_assets]

        return JsonResponse({
            'success': True,
            'data_blocks': data_blocks,
            'total_blocks': len(data_blocks)
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)
