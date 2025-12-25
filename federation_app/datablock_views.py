"""
数据块管理相关视图
"""
import json
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from .datablock_service import datablock_market_service, datablock_init_service


@require_http_methods(["GET"])
def get_datablock_market(request):
    """获取数据块市场 - 显示可购买的数据块"""
    try:
        dataset_type = request.GET.get('dataset_type', 'CIFAR10')
        limit = int(request.GET.get('limit', 100))

        available_blocks = datablock_market_service.get_available_blocks(
            dataset_type=dataset_type,
            limit=limit
        )

        market_stats = datablock_market_service.get_market_stats()

        return JsonResponse({
            'success': True,
            'available_blocks': available_blocks,
            'total_available': len(available_blocks),
            'market_stats': market_stats
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@require_http_methods(["GET"])
@login_required
def get_my_datablocks(request):
    """获取我的数据块"""
    try:
        user = request.user
        my_blocks = datablock_market_service.get_user_blocks(user)

        return JsonResponse({
            'success': True,
            'my_blocks': my_blocks,
            'total_blocks': len(my_blocks),
            'virtual_coins': user.virtual_coins
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
@login_required
def purchase_datablock(request):
    """购买数据块"""
    try:
        data = json.loads(request.body)
        block_id = data.get('block_id')

        if block_id is None:
            return JsonResponse({'success': False, 'error': '数据块ID不能为空'})

        user = request.user
        result = datablock_market_service.purchase_block(user, block_id)

        return JsonResponse(result)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
@login_required
def sell_datablock(request):
    """出售数据块回系统"""
    try:
        data = json.loads(request.body)
        block_id = data.get('block_id')

        if block_id is None:
            return JsonResponse({'success': False, 'error': '数据块ID不能为空'})

        user = request.user
        result = datablock_market_service.sell_block(user, block_id)

        return JsonResponse(result)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@require_http_methods(["GET"])
@login_required
def get_datablock_transactions(request):
    """获取我的数据块交易记录"""
    try:
        from .models import DataBlockTransaction

        user = request.user
        transactions = DataBlockTransaction.objects.filter(user=user).order_by('-created_at')[:50]

        transactions_data = [{
            'id': t.id,
            'block_id': t.data_block.block_id,
            'transaction_type': t.transaction_type,
            'transaction_type_display': t.get_transaction_type_display(),
            'price': t.price,
            'coins_before': t.coins_before,
            'coins_after': t.coins_after,
            'description': t.description,
            'created_at': t.created_at.strftime('%Y-%m-%d %H:%M:%S')
        } for t in transactions]

        return JsonResponse({
            'success': True,
            'transactions': transactions_data,
            'total_count': len(transactions_data)
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@require_http_methods(["GET"])
def get_datablock_stats(request):
    """获取数据块市场统计信息"""
    try:
        stats = datablock_market_service.get_market_stats()

        return JsonResponse({
            'success': True,
            'stats': stats
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
@login_required
def initialize_datablocks(request):
    """初始化数据块到数据库（管理员功能）"""
    try:
        # 检查管理员权限
        if not request.user.is_staff and not request.user.is_superuser:
            return JsonResponse({
                'success': False,
                'error': '需要管理员权限'
            }, status=403)

        data = json.loads(request.body)
        dataset_type = data.get('dataset_type', 'CIFAR10')

        result = datablock_init_service.initialize_datablocks(dataset_type)

        return JsonResponse(result)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)
